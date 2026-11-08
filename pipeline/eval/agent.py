"""RET-10c: retrieval_agent, AGENT_PROMPT and agent_tools: the loop that searches, reads and lists until the question is answered.

Today a fixed script decides every query and when to stop, and 69 of the 470 questions with gold
documents still miss some: 126 documents, 64 outside the saved top 200 (audit 2026-11-08). qst_0437
("Across all incident postmortems, which Redwood team was assigned the most follow-up action
items?") has 9 gold Confluence pages; the script submits 40 Slack and Gmail messages and none of
them. A query written after reading real documents, or a title listing when the question says
"all", reaches them. So the model runs the loop: a LlamaIndex FunctionAgent with `search` (today's
retriever and reranker as RET-10a blocks), `read` (RET-10b) and `list_titles` (RET-9a). The state
keeps the ledger, the ids read, which is what a run submits (RET-10d): PipesHub's rule, the reason
its extra-document count is 0.4 against our 3.9. The budget is 8 tool-using model calls (parallel
tool calls in one model call count once); then LlamaIndex asks for an answer from what was
gathered instead of raising. The prompt is generic: nothing about question types or scoring.

    >>> from pipeline.eval.titles import TitleList
    >>> print(titles_text(TitleList(rows=[("confluence", "dsid_a", "Postmortem: Streaming stalls")], total=73)))
    73 titles match; showing 1
    dsid_a | Postmortem: Streaming stalls
"""
import asyncio
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

import pyarrow as pa
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.llms import LLM
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

from pipeline.eval.agent_tools import chunks_by_document, read_document, search_snippets
from pipeline.eval.answers import answer_of, quotes_of
from pipeline.eval.titles import TitleList, titles_like

MAX_ITERATIONS = 8  # tool-using model calls per question; PipesHub caps a sub-agent at 8 turns

AGENT_PROMPT = """You answer questions from a company's internal documents using three tools.

How to work:
1. Start with one short, broad search. Do not write long queries.
2. Read in full the 1 to 3 documents your answer will rest on. A search snippet can hold an outdated value, half a list or a step without its condition; the whole document settles it. Never answer from snippets alone.
3. After reading, write down which parts of the question still have no quote. For each, search again using the words the documents use (the system, team, customer, ticket or document names you saw), not the question's words.
4. When the question asks for all, every, each or how many of something, do not sample with search: list the titles that match (list_titles), then read the ones the question needs.
5. Stop when every part of the question is supported by a quote from a document you read, or when you have nothing new to try.

How to answer, inside two tags:
<quotes> the exact sentences from the documents you read that support each part of the answer, each with its document id </quotes>
<answer> The first sentence answers the question directly. Give values exactly as written, with their units and qualifiers. Give a procedure or list from the one document that defines it, complete, in order. If two documents disagree about the same thing, prefer the one that explicitly supersedes the other, then the narrower scope, then the more recent, and say in a few words which one you followed. Say when the documents do not answer a part. </answer>
"""


class AgentAnswer(NamedTuple):
    answer: str
    quotes: str
    read: List[str]  # the ledger: document ids read in full, in read order
    iterations: int  # model calls, the forced final answer included when the budget cut the loop
    budget_exhausted: bool  # the loop hit MAX_ITERATIONS and the answer was forced from what was gathered


def titles_text(result: TitleList) -> str:
    """The list tool's text: the total, then one `doc_id | title` line per row."""
    return f"{result.total} titles match; showing {len(result.rows)}\n" + "\n".join(f"{doc_id} | {title}" for _, doc_id, title in result.rows)


def agent_tools(retriever: BaseRetriever, titles: Dict[str, Tuple[str, str]], table: pa.Table, documents: Dict[str, Tuple[str, str]],
                parquet_path: Optional[Union[str, Path]]) -> List[FunctionTool]:
    """search, read and list_titles as FunctionTools. The store holds "state" = {"read": [...]} (the ledger) and "seen"
    (ids any search showed, for the (seen) marker); parallel tool calls run concurrently, so updates go through `edit_state`."""
    async def search(ctx: Context, query: str, source: Optional[str] = None) -> str:
        """Search the documents. Returns up to 10 documents, best first: id, title, source, how many chunks matched, two snippets. `source` narrows to one of confluence, slack, gmail, github, google_drive, jira, linear, hubspot, fireflies."""
        ranked = retriever.retrieve(query)
        async with ctx.store.edit_state() as store:
            text = search_snippets(ranked, titles, source=source, read=store["state"]["read"], seen=store.get("seen", []))
            store["seen"] = list(dict.fromkeys(store.get("seen", []) + list(chunks_by_document(ranked, titles, source))))
        return text

    async def read(ctx: Context, doc_id: str, start: int = 0) -> str:
        """Read one whole document by its id (from search or list_titles). Long documents come in windows; the text says how to continue."""
        async with ctx.store.edit_state() as store:
            if doc_id in store["state"]["read"] and start == 0:
                return f"{doc_id} already read"
            text = read_document(doc_id, documents, parquet_path, start=start)
            if not text.startswith("No document"):  # a mistyped id never enters the ledger
                store["state"]["read"] = list(dict.fromkeys(store["state"]["read"] + [doc_id]))
        return text

    def list_titles(source: Optional[str], pattern: str) -> str:
        """List every document whose title contains `pattern` (case-insensitive), up to 200, with the total. Use it for all / every / how many questions. `source` as in search, or null for all sources."""
        return titles_text(titles_like(table, source, pattern))

    return [FunctionTool.from_defaults(async_fn=search, name="search"), FunctionTool.from_defaults(async_fn=read, name="read"),
            FunctionTool.from_defaults(fn=list_titles, name="list_titles")]


def retrieval_agent(llm: LLM, tools: Sequence[FunctionTool]) -> FunctionAgent:
    """The loop: the three tools, the generic prompt, the ledger in state, an answer forced at the budget instead of an error."""
    return FunctionAgent(tools=list(tools), llm=llm, system_prompt=AGENT_PROMPT, initial_state={"read": []}, early_stopping_method="generate")


async def aanswer_question(agent: FunctionAgent, question: str, max_iterations: int = MAX_ITERATIONS) -> AgentAnswer:
    """The async body of answer_question, for callers already inside an event loop (the Ask page)."""
    handler = agent.run(question, max_iterations=max_iterations + 1)  # the library counts the answering call too
    response = str(await handler)
    state, calls = await handler.ctx.store.get("state"), await handler.ctx.store.get("num_iterations")
    return AgentAnswer(answer_of(response), quotes_of(response), state["read"], calls, calls > max_iterations)


def answer_question(agent: FunctionAgent, question: str, max_iterations: int = MAX_ITERATIONS) -> AgentAnswer:
    """Run the loop on one question: the parsed answer and quotes, the ledger, the model calls used, whether the budget cut it."""
    return asyncio.run(aanswer_question(agent, question, max_iterations))

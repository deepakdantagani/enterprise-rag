"""RET-10c: retrieval_agent, AGENT_PROMPT and agent_tools: the loop that searches, reads and lists until the question is answered.
RET-10e-c: RetrievalAgent, whose forced answer at the budget names what was read and keeps the answer shape.

Today a fixed script decides every query and when to stop, and 69 of the 470 questions with gold
documents still miss some: 126 documents, 64 outside the saved top 200 (audit 2026-11-08). qst_0437
("Across all incident postmortems, which Redwood team was assigned the most follow-up action
items?") has 9 gold Confluence pages; the script submits 40 Slack and Gmail messages and none of
them. A query written after reading real documents, or a title listing when the question says
"all", reaches them. So the model runs the loop: a LlamaIndex FunctionAgent with `search` (today's
retriever and reranker as RET-10a blocks), `read` (RET-10b) and `list_titles` (RET-9a). The state
keeps the ledger, the ids read, which is what a run submits (RET-10d): PipesHub's rule, the reason
its extra-document count is 0.4 against our 3.9. The budget is 8 tool-using model calls (parallel
tool calls in one model call count once); then an answer is forced from what was gathered
instead of raising. On the second smoke run (2026-11-08, qst_0437, 10 model calls, 3 reads) Haiku's
forced answer was "I did not search or read any incident postmortems", with no tags. The cause is in
the library (llama-index-core 0.14.24): its forced call sends the system prompt, the memory and its
"summarize what you have learned" text, but during a run the memory holds only the question; the
turn's tool calls and results sit in the scratchpad until finalize. The model saw no history, so it
had read nothing. RetrievalAgent overrides that one call: the scratchpad goes in, and the appended
system message lists the ledger with titles and asks for <quotes> then <answer>. The prompts are
generic: nothing about question types or scoring.

    >>> print(stop_prompt(["dsid_a"], {"dsid_a": ("confluence", "Postmortem: Streaming stalls")}).splitlines()[1])
      dsid_a | Postmortem: Streaming stalls

    >>> from pipeline.eval.titles import TitleList
    >>> print(titles_text(TitleList(rows=[("confluence", "dsid_a", "Postmortem: Streaming stalls")], total=73)))
    73 titles match; showing 1
    dsid_a | Postmortem: Streaming stalls
"""
import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

import pyarrow as pa
from llama_index.core.agent.workflow import AgentOutput, FunctionAgent, ToolCallResult
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.bridge.pydantic import Field
from llama_index.core.llms import LLM, ChatMessage
from llama_index.core.memory import BaseMemory
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context, StopEvent

from pipeline.eval.agent_tools import NO_TITLE, chunks_by_document, read_document, search_snippets
from pipeline.eval.answers import answer_of, quotes_of
from pipeline.eval.titles import DEFAULT_LIMIT, TitleList, title_groups, titles_like

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

STOP_BUDGET = "Your tool budget is used up; no more tool calls. "  # the opening; stop_prompt() builds the whole message
STOP_READ = """You read these documents in full:
{lines}
Answer the question now from them, in the same shape as always: <quotes> with the exact sentences and each document's id, then <answer>. For any part of the question these documents do not answer, say so inside <answer>. Do not say that nothing was read."""
STOP_NOTHING_READ = """You read no document in full. Answer in the same shape as always: an empty <quotes>, then <answer> saying that the documents the question needs were not found, with anything the search results did show."""


class AgentAnswer(NamedTuple):
    answer: str
    quotes: str
    read: List[str]  # the ledger: document ids read in full, in read order
    iterations: int  # model calls, the forced final answer included when the budget cut the loop
    budget_exhausted: bool  # the loop hit MAX_ITERATIONS and the answer was forced from what was gathered


def stop_prompt(read: Sequence[str], titles: Dict[str, Tuple[str, str]]) -> str:
    """The system message for the forced answer: the ledger as `doc_id | title` lines, then how to answer."""
    lines = "\n".join(f"  {doc_id} | {titles.get(doc_id, NO_TITLE)[1]}" for doc_id in read)
    return STOP_BUDGET + (STOP_READ.format(lines=lines) if read else STOP_NOTHING_READ)


class RetrievalAgent(FunctionAgent):
    """FunctionAgent whose forced answer at the budget uses stop_prompt over the ledger instead of the library's text."""

    titles: Dict[str, Tuple[str, str]] = Field(default_factory=dict, description="doc_id -> (source_type, title) for the ledger lines")

    async def _generate_early_stopping_response(self, ctx: Context, max_iterations: int) -> StopEvent:
        # Mirrors BaseWorkflowAgent._generate_early_stopping_response (llama-index-core 0.14.24) with two changes: the
        # scratchpad (this run's tool calls and results, flushed to memory only in finalize) is included, where the library
        # sends the question alone and so asks for an answer from nothing; and the appended message is stop_prompt.
        # max_iterations is unused: the library prints the number in its message, ours does not. AgentWorkflow (multi-agent)
        # has its own copy of this method and never calls the agent's, so there the library behaviour would return.
        memory: BaseMemory = await ctx.store.get("memory")
        messages = await memory.aget()
        scratchpad: List[ChatMessage] = await ctx.store.get(self.scratchpad_key, default=[])
        if scratchpad and scratchpad[-1].role == "assistant":
            # The turn that hit the budget. With tool calls, they never ran and the API rejects a tool_use without its tool_result;
            # as a text answer it would be a prefill, which the API rejects under thinking (the library throws that answer away too).
            scratchpad = scratchpad[:-1]
        state = await ctx.store.get("state", default={"read": []})
        llm_input = ([ChatMessage(role="system", content=self.system_prompt)] if self.system_prompt else []) + list(messages) + list(scratchpad)
        llm_input.append(ChatMessage(role="system", content=stop_prompt(state.get("read", []), self.titles)))  # system role, as the library's
        response = await self._get_llm_response(ctx, llm_input)
        await memory.aput(response.message)
        output = AgentOutput(response=response.message, tool_calls=[], raw=response.raw, current_agent_name=self.name)
        tool_calls: List[ToolCallResult] = await ctx.store.get("current_tool_calls", default=[])
        output.tool_calls.extend(tool_calls)  # type: ignore[arg-type]  # copied from the library: ToolCallResult objects in a field typed ToolSelection
        await ctx.store.set("current_tool_calls", [])
        ctx.write_event_to_stream(output)
        return StopEvent(result=output)


def titles_text(result: TitleList, limit: int = DEFAULT_LIMIT) -> str:
    """The list tool's text: the total, then one `doc_id | title` line per row. Given more rows than `limit` (the tool passes
    every match), the title groups instead (RET-10e-b); a list already capped by titles_like prints its rows as before."""
    if len(result.rows) <= limit:
        return f"{result.total} titles match; showing {len(result.rows)}\n" + "\n".join(f"{doc_id} | {title}" for _, doc_id, title in result.rows)
    summary = title_groups(result.rows)
    smaller = len(result.rows) - sum(count for count, _, _ in summary.groups) - summary.singletons  # groups past the top, if any
    return (f"{result.total} titles match, more than the {limit} this tool lists. Largest title groups (the text before ':', ' — ' or ' ('):\n"
            + "".join(f"  {count} | {source} | {group}\n" for count, source, group in summary.groups)
            + (f"{smaller} titles are in smaller groups.\n" if smaller else "") + f"{summary.singletons} titles are in groups of one.\n"
            "Narrow with a longer pattern (for a 'Name:' family, the name with its ':') or a source; when a group's titles are all the same (a channel), search instead.")


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
        """List every document whose title contains `pattern` (case-insensitive), up to 200, with the total; past 200, the largest title groups to narrow by. Use it for all / every / how many questions. `source` as in search, or null for all sources."""  # "200" is DEFAULT_LIMIT; the model reads this literal, so the two move together
        return titles_text(titles_like(table, source, pattern, limit=None))

    return [FunctionTool.from_defaults(async_fn=search, name="search"), FunctionTool.from_defaults(async_fn=read, name="read"),
            FunctionTool.from_defaults(fn=list_titles, name="list_titles")]


def retrieval_agent(llm: LLM, tools: Sequence[FunctionTool], titles: Dict[str, Tuple[str, str]]) -> FunctionAgent:
    """The loop: the three tools, the generic prompt, the ledger in state, our stop prompt at the budget instead of an error.
    `titles` is the same doc_id -> (source_type, title) dict agent_tools takes; the stop message prints the ledger with it."""
    return RetrievalAgent(tools=list(tools), llm=llm, system_prompt=AGENT_PROMPT, initial_state={"read": []},
                          early_stopping_method="generate", titles=titles)


async def aanswer_question(agent: FunctionAgent, question: str, max_iterations: int = MAX_ITERATIONS,
                           on_event: Optional[Callable[[Any], None]] = None) -> AgentAnswer:
    """The async body of answer_question, for callers already inside an event loop (the Ask page).

    `on_event` sees every workflow event (ToolCallResult, AgentOutput, ...): the runner (RET-10d) builds its trace from them.
    """
    handler = agent.run(question, max_iterations=max_iterations + 1)  # the library counts the answering call too
    if on_event is not None:
        async for event in handler.stream_events():
            on_event(event)
    response = str(await handler)
    state, calls = await handler.ctx.store.get("state"), await handler.ctx.store.get("num_iterations")
    return AgentAnswer(answer_of(response), quotes_of(response), state["read"], calls, calls > max_iterations)


def answer_question(agent: FunctionAgent, question: str, max_iterations: int = MAX_ITERATIONS) -> AgentAnswer:
    """Run the loop on one question: the parsed answer and quotes, the ledger, the model calls used, whether the budget cut it."""
    return asyncio.run(aanswer_question(agent, question, max_iterations))

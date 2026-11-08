"""RET-10c: retrieval_agent, AGENT_PROMPT and agent_tools: the loop over search, read and list with a ledger.

Run: uv run python -m unittest tests.test_eval_agent
"""
import doctest
import sys
import unittest
from pathlib import Path

import pyarrow as pa
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import TextBlock, ToolCallBlock
from llama_index.core.llms import ChatMessage
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import agent as agent_module  # noqa: E402
from pipeline.eval.agent import AGENT_PROMPT, AgentAnswer, agent_tools, answer_question, retrieval_agent  # noqa: E402

TITLES = {"dsid_a": ("confluence", "Postmortem: Streaming stalls"), "dsid_b": ("slack", "incidents | eng")}  # a title with " | "
TABLE = pa.Table.from_pylist([{"doc_id": d, "source_type": s, "title": t} for d, (s, t) in TITLES.items()])
DOCS = {"dsid_a": ("Postmortem: Streaming stalls", "Action items: platform team, 3."), "dsid_b": ("incidents | eng", "sam: paged")}
ANSWER = [TextBlock(text='<quotes>\n"Action items: platform team, 3."\n</quotes>\n<answer>\nThe platform team, with 3.\n</answer>')]
BUDGET_PROMPT = "maximum number of iterations"  # the library's early-stopping prompt (llama-index-core 0.14.24, agent/workflow/prompts.py)


class FakeRetriever(BaseRetriever):
    def _retrieve(self, query_bundle):
        return [NodeWithScore(node=TextNode(text=f"{query_bundle.query_str} in {d}", relationships={
            NodeRelationship.SOURCE: RelatedNodeInfo(node_id=d)}), score=1.0) for d in ("dsid_a", "dsid_b")]


def call(name, **kwargs):
    return ToolCallBlock(tool_call_id=f"{name}-{sorted(kwargs.items())}", tool_name=name, tool_kwargs=kwargs)


def scripted_llm(*steps, log):
    """A tool-calling LLM that answers each call with the next scripted blocks (the last one repeats) and logs every tool result."""
    def generate(messages, **kwargs):
        log.extend(str(m.content) for m in messages if m.role == "tool")
        if any(BUDGET_PROMPT in str(m.content) for m in messages):
            return ChatMessage(role="assistant", content="<answer>Best answer from what was read.</answer>")
        blocks = steps[min(len(log) and sum(1 for m in messages if m.role == "assistant"), len(steps) - 1)]
        return ChatMessage(role="assistant", blocks=list(blocks))
    return MockFunctionCallingLLM(response_generator=generate)


def run(*steps, max_iterations=8, log=None):
    tools = agent_tools(FakeRetriever(), TITLES, TABLE, dict(DOCS), parquet_path=None)
    return answer_question(retrieval_agent(scripted_llm(*steps, log=[] if log is None else log), tools), "Which team had the most action items?", max_iterations)


class RetrievalAgent(unittest.TestCase):
    def test_search_then_read_then_answer_gives_the_parsed_answer_and_a_ledger_of_one(self):
        result = run([call("search", query="action items")], [call("read", doc_id="dsid_a")], ANSWER)
        self.assertEqual(result, AgentAnswer("The platform team, with 3.", '"Action items: platform team, 3."', ["dsid_a"], 3, False))

    def test_an_answer_on_the_last_allowed_call_is_kept(self):
        result = run([call("search", query="a")], [call("search", query="b")], ANSWER, max_iterations=3)
        self.assertEqual((result.answer, result.iterations, result.budget_exhausted), ("The platform team, with 3.", 3, False))

    def test_a_model_that_never_stops_is_cut_at_the_budget_and_still_answers(self):
        result = run([call("search", query="again")], max_iterations=4)
        self.assertEqual((result.iterations, result.budget_exhausted, result.read, result.answer), (5, True, [], "Best answer from what was read."))

    def test_two_reads_in_one_step_are_one_iteration_and_both_enter_the_ledger(self):
        result = run([call("read", doc_id="dsid_a"), call("read", doc_id="dsid_b")], ANSWER)
        self.assertEqual((result.read, result.iterations), (["dsid_a", "dsid_b"], 2))

    def test_a_repeated_read_says_so_and_an_unknown_id_never_enters_the_ledger(self):
        log = []
        result = run([call("read", doc_id="dsid_a")], [call("read", doc_id="dsid_a"), call("read", doc_id="dsid_zz")], ANSWER, log=log)
        self.assertEqual(result.read, ["dsid_a"])
        self.assertIn("dsid_a already read", log)
        self.assertIn("No document with id dsid_zz", log)

    def test_a_second_search_marks_the_documents_already_shown_or_read_even_with_a_bar_in_the_title(self):
        log = []
        run([call("search", query="one")], [call("read", doc_id="dsid_a")], [call("search", query="two")], ANSWER, log=log)
        second = [text for text in log if "[1]" in text][-1]  # the log repeats history; the last one is the second search
        self.assertIn("dsid_a | 1 chunk matched, 1 shown (read)", second)
        self.assertIn("incidents | eng | slack | dsid_b | 1 chunk matched, 1 shown (seen)", second)

    def test_the_prompt_carries_no_benchmark_words_and_states_the_rules(self):
        self.assertFalse([w for w in ("qst_", "gold", "judge", "question_type", "benchmark", "leaderboard") if w in AGENT_PROMPT.lower()])
        self.assertEqual([r for r in ("read", "search again", "all", "quote") if r not in AGENT_PROMPT.lower()], [])

    def test_the_three_tools_are_named_for_the_model_and_list_titles_prints_total_then_lines(self):
        search, read, list_titles = agent_tools(FakeRetriever(), TITLES, TABLE, dict(DOCS), parquet_path=None)
        self.assertEqual([t.metadata.name for t in (search, read, list_titles)], ["search", "read", "list_titles"])
        self.assertEqual(list_titles.call(source="confluence", pattern="postmortem").content, "1 titles match; showing 1\ndsid_a | Postmortem: Streaming stalls")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(agent_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

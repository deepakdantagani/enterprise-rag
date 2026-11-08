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
LIBRARY_STOP = "maximum number of iterations"  # the library's early-stopping prompt (llama-index-core 0.14.24, agent/workflow/prompts.py)
BUDGET_PROMPT = "tool budget is used up"  # ours (RET-10e-c)


class FakeRetriever(BaseRetriever):
    def _retrieve(self, query_bundle):
        return [NodeWithScore(node=TextNode(text=f"{query_bundle.query_str} in {d}", relationships={
            NodeRelationship.SOURCE: RelatedNodeInfo(node_id=d)}), score=1.0) for d in ("dsid_a", "dsid_b")]


def call(name, **kwargs):
    return ToolCallBlock(tool_call_id=f"{name}-{sorted(kwargs.items())}", tool_name=name, tool_kwargs=kwargs)


def scripted_llm(*steps, log, seen=None):
    """A tool-calling LLM that answers each call with the next scripted blocks (the last one repeats), logs every tool result,
    and appends each call's messages to `seen`."""
    def generate(messages, **kwargs):
        log.extend(str(m.content) for m in messages if m.role == "tool")
        if seen is not None:
            seen.append(list(messages))
        if any(BUDGET_PROMPT in str(m.content) for m in messages):
            return ChatMessage(role="assistant", content="<answer>Best answer from what was read.</answer>")
        blocks = steps[min(len(log) and sum(1 for m in messages if m.role == "assistant"), len(steps) - 1)]
        return ChatMessage(role="assistant", blocks=list(blocks))
    return MockFunctionCallingLLM(response_generator=generate)


def run(*steps, max_iterations=8, log=None, seen=None):
    tools = agent_tools(FakeRetriever(), TITLES, TABLE, dict(DOCS), parquet_path=None)
    agent = retrieval_agent(scripted_llm(*steps, log=[] if log is None else log, seen=seen), tools, titles=TITLES)
    return answer_question(agent, "Which team had the most action items?", max_iterations)


class Loop(unittest.TestCase):
    def test_search_then_read_then_answer_gives_the_parsed_answer_and_a_ledger_of_one(self):
        result = run([call("search", query="action items")], [call("read", doc_id="dsid_a")], ANSWER)
        self.assertEqual(result, AgentAnswer("The platform team, with 3.", '"Action items: platform team, 3."', ["dsid_a"], 3, False))

    def test_an_answer_on_the_last_allowed_call_is_kept(self):
        result = run([call("search", query="a")], [call("search", query="b")], ANSWER, max_iterations=3)
        self.assertEqual((result.answer, result.iterations, result.budget_exhausted), ("The platform team, with 3.", 3, False))

    def test_a_model_that_never_stops_is_cut_at_the_budget_and_still_answers(self):
        result = run([call("search", query="again")], max_iterations=4)
        self.assertEqual((result.iterations, result.budget_exhausted, result.read, result.answer), (5, True, [], "Best answer from what was read."))

    def test_the_forced_call_carries_our_stop_message_with_the_ledger_s_ids_and_titles_not_the_library_s(self):
        seen = []
        run([call("read", doc_id="dsid_a")], [call("search", query="again")], max_iterations=3, seen=seen)
        last = seen[-1][-1]
        self.assertEqual(last.role, "system")
        self.assertIn("dsid_a | Postmortem: Streaming stalls", str(last.content))
        self.assertTrue(all(LIBRARY_STOP not in str(m.content) for m in seen[-1]))

    def test_the_forced_call_with_nothing_read_says_so_and_still_asks_for_the_two_tags(self):
        seen = []
        result = run([call("search", query="again")], max_iterations=2, seen=seen)
        text = str(seen[-1][-1].content)
        self.assertIn("read no document in full", text)
        self.assertIn("<quotes>", text)
        self.assertEqual((result.budget_exhausted, result.answer), (True, "Best answer from what was read."))

    def test_the_forced_call_sees_the_whole_turn_so_far_plus_our_message_and_nothing_is_removed(self):
        seen = []
        run([call("search", query="again")], max_iterations=3, seen=seen)
        before, forced = seen[-2], seen[-1]
        self.assertEqual([(m.role, str(m.content)) for m in before], [(m.role, str(m.content)) for m in forced[:len(before)]])
        self.assertEqual([m.role for m in forced[len(before):]], ["system"])  # the turn that hit the budget is dropped: its call never ran
        self.assertEqual(forced[-2].role, "tool")  # never a dangling tool_use, never an assistant prefill
        self.assertTrue(any("again in dsid_a" in str(m.content) for m in forced))  # the library's own forced call sends the question alone

    def test_an_answer_arriving_on_the_call_past_the_budget_is_not_sent_back_as_a_prefill(self):
        seen = []
        result = run([call("search", query="a")], [call("search", query="b")], [call("read", doc_id="dsid_a")], ANSWER, max_iterations=3, seen=seen)
        self.assertEqual([m.role for m in seen[-1][-3:]], ["assistant", "tool", "system"])
        self.assertEqual((result.budget_exhausted, result.read), (True, ["dsid_a"]))

    def test_the_stop_message_names_no_question_source_or_score(self):
        from pipeline.eval.agent import STOP_BUDGET, STOP_NOTHING_READ, STOP_READ
        text = (STOP_BUDGET + STOP_READ + STOP_NOTHING_READ).lower()
        self.assertFalse(any(w in text for w in ("postmortem", "redwood", "confluence", "slack", "score", "judge")))

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

    def test_a_cut_list_prints_the_total_the_largest_groups_and_the_singletons_instead_of_lines(self):
        from pipeline.eval.agent import titles_text
        from pipeline.eval.titles import TitleList
        rows = [("confluence", "dsid_a", "Postmortem: Streaming stalls"), ("confluence", "dsid_b", "Postmortem: Latency regression"), ("slack", "dsid_c", "postmortems")]
        self.assertEqual(titles_text(TitleList(rows=rows, total=3), limit=2),
                         "3 titles match, more than the 2 this tool lists. Largest title groups (the text before ':', ' — ' or ' ('):\n"
                         "  2 | confluence | Postmortem\n1 titles are in groups of one.\n"
                         "Narrow with a longer pattern (for a 'Name:' family, the name with its ':') or a source; when a group's titles are all the same (a channel), search instead.")

    def test_a_list_already_capped_by_titles_like_prints_its_rows_not_groups_over_a_partial_list(self):
        from pipeline.eval.agent import titles_text
        from pipeline.eval.titles import TitleList
        capped = TitleList(rows=[("confluence", "dsid_a", "Postmortem: Streaming stalls")], total=1468)
        self.assertEqual(titles_text(capped), "1468 titles match; showing 1\ndsid_a | Postmortem: Streaming stalls")

    def test_list_titles_returns_the_groups_when_more_than_the_limit_match(self):
        big = pa.Table.from_pylist([{"doc_id": f"dsid_{i}", "source_type": "slack", "title": f"eng-security: thread {i}"} for i in range(201)])
        _, _, list_titles = agent_tools(FakeRetriever(), TITLES, big, dict(DOCS), parquet_path=None)
        text = list_titles.call(source=None, pattern="eng-security").content
        self.assertTrue(text.startswith("201 titles match, more than the 200 this tool lists."), text)
        self.assertIn("  201 | slack | eng-security\n", text)
        self.assertNotIn("smaller groups", text)
        self.assertNotIn("dsid_", text)

    def test_groups_past_the_top_eight_are_counted_in_a_smaller_groups_line_so_the_counts_add_up(self):
        from pipeline.eval.agent import titles_text
        from pipeline.eval.titles import TitleList
        rows = [("slack", f"{name}{i}", name) for name in "abcdefghi" for i in range(2)] + [("slack", "x", "lone")]  # 9 groups of 2, 1 alone
        text = titles_text(TitleList(rows=rows, total=19), limit=3)
        self.assertEqual(text.count(" | slack | "), 8)
        self.assertIn("  2 | slack | h\n2 titles are in smaller groups.\n1 titles are in groups of one.\n", text)

    def test_the_three_tools_are_named_for_the_model_and_list_titles_prints_total_then_lines(self):
        search, read, list_titles = agent_tools(FakeRetriever(), TITLES, TABLE, dict(DOCS), parquet_path=None)
        self.assertEqual([t.metadata.name for t in (search, read, list_titles)], ["search", "read", "list_titles"])
        self.assertEqual(list_titles.call(source="confluence", pattern="postmortem").content, "1 titles match; showing 1\ndsid_a | Postmortem: Streaming stalls")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(agent_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

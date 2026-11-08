"""RET-10d: agent_answers, the loop over a question set: resumable rows for the judges, a trace sidecar, batch prefetch.

Run: uv run python -m unittest tests.test_eval_agent_run
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import TextBlock, ToolCallBlock
from llama_index.core.llms import ChatMessage
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import agent_run as agent_run_module  # noqa: E402
from pipeline.eval.agent import agent_tools, retrieval_agent  # noqa: E402
from pipeline.eval.agent_run import agent_answers, candidate_ids, candidate_prefetcher, finished_rows, usage_of  # noqa: E402

TITLES = {"dsid_a": ("confluence", "Postmortem: Streaming stalls")}
TABLE = pa.Table.from_pylist([{"doc_id": "dsid_a", "source_type": "confluence", "title": "Postmortem: Streaming stalls"}])
DOCS = {"dsid_a": ("Postmortem: Streaming stalls", "Action items: platform team, 3.")}
QUESTIONS = [{"question_id": "qst_0001", "question": "Which team?"}, {"question_id": "qst_0002", "question": "How many?"}]
ANSWER = '<quotes>\n"Action items: platform team, 3."\n</quotes>\n<answer>\nThe platform team.\n</answer>'


class FakeRetriever(BaseRetriever):
    def _retrieve(self, query_bundle):  # search hits dsid_b; the agent reads dsid_a, so the two can be told apart
        node = TextNode(text="x in dsid_b", relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id="dsid_b")})
        return [NodeWithScore(node=node, score=1.0)]


def scripted_agent(calls, fail_on=None):
    """search, read, answer for every question; `calls` counts the model calls; `fail_on` makes one question's model raise."""
    def generate(messages, **kwargs):
        calls.append(1)
        if fail_on and any(fail_on in str(m.content) for m in messages if m.role == "user"):
            raise RuntimeError("model down")
        turn = sum(1 for m in messages if m.role == "assistant")
        blocks = [[ToolCallBlock(tool_call_id="s", tool_name="search", tool_kwargs={"query": "team"})],
                  [ToolCallBlock(tool_call_id="r", tool_name="read", tool_kwargs={"doc_id": "dsid_a"})], [TextBlock(text=ANSWER)]][min(turn, 2)]
        return ChatMessage(role="assistant", blocks=blocks)
    return retrieval_agent(MockFunctionCallingLLM(response_generator=generate), agent_tools(FakeRetriever(), TITLES, TABLE, dict(DOCS), None))


class AgentAnswers(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.out, self.trace = Path(self.folder.name) / "answers.jsonl", Path(self.folder.name) / "trace.jsonl"

    def tearDown(self):
        self.folder.cleanup()

    def rows(self, path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_one_row_per_question_in_the_leaderboard_shape_with_the_ledger_as_document_ids(self):
        self.assertEqual(agent_answers(scripted_agent([]), QUESTIONS, self.out, self.trace), 2)
        rows = self.rows(self.out)
        self.assertEqual([r["question_id"] for r in rows], ["qst_0001", "qst_0002"])
        self.assertEqual(rows[0], {"question_id": "qst_0001", "answer": "The platform team.", "document_ids": ["dsid_a"],
                                   "quotes": '"Action items: platform team, 3."', "iterations": 3, "budget_exhausted": False,
                                   "input_tokens": 0, "output_tokens": 0})

    def test_a_re_run_asks_the_model_nothing_and_adds_no_row(self):
        agent_answers(scripted_agent([]), QUESTIONS, self.out, self.trace)
        calls = []
        self.assertEqual(agent_answers(scripted_agent(calls), QUESTIONS, self.out, self.trace), 0)
        self.assertEqual((calls, len(self.rows(self.out))), ([], 2))

    def test_the_trace_sidecar_holds_every_tool_call_with_its_arguments_and_result_size(self):
        agent_answers(scripted_agent([]), QUESTIONS[:1], self.out, self.trace)
        trace = self.rows(self.trace)[0]
        self.assertEqual([(c["tool"], c["args"]) for c in trace["tool_calls"]], [("search", {"query": "team"}), ("read", {"doc_id": "dsid_a"})])
        self.assertTrue(all(c["chars"] > 0 for c in trace["tool_calls"]))
        self.assertEqual((trace["question_id"], trace["model_calls"]), ("qst_0001", 3))

    def test_prefetch_is_called_once_per_batch_with_that_batch_s_question_ids(self):
        batches = []
        agent_answers(scripted_agent([]), QUESTIONS, self.out, self.trace, prefetch=batches.append, batch=1)
        self.assertEqual(batches, [["qst_0001"], ["qst_0002"]])

    def test_a_crash_on_the_second_question_leaves_the_first_row_on_disk_and_a_rerun_resumes(self):
        with self.assertRaises(RuntimeError):
            agent_answers(scripted_agent([], fail_on="How many?"), QUESTIONS, self.out, self.trace)
        self.assertEqual([r["question_id"] for r in self.rows(self.out)], ["qst_0001"])
        self.assertEqual(agent_answers(scripted_agent([]), QUESTIONS, self.out, self.trace), 1)

    def test_a_line_cut_by_a_crash_is_dropped_so_the_run_resumes_and_appends_cleanly(self):
        self.out.write_text('{"question_id": "qst_0001", "answer": "a", "document_ids": []}\n{"question_id": "qst_00')
        self.assertEqual([r["question_id"] for r in finished_rows(self.out)], ["qst_0001"])
        self.assertEqual(agent_answers(scripted_agent([]), QUESTIONS, self.out, self.trace), 1)
        self.assertEqual([r["question_id"] for r in self.rows(self.out)], ["qst_0001", "qst_0002"])

    def test_usage_is_summed_from_raw_responses_with_cached_tokens_and_zero_without_them(self):
        raw = {"usage": SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=300, cache_creation_input_tokens=0)}
        self.assertEqual(usage_of(raw), (1500, 80))
        self.assertEqual(usage_of(None), (0, 0))
        self.assertEqual(usage_of({"usage": {"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": None}}), (5, 7))

    def test_the_prefetcher_scans_once_per_batch_and_skips_documents_already_cached(self):
        import pyarrow.parquet as pq
        path = Path(self.folder.name) / "documents.parquet"
        pq.write_table(pa.Table.from_pylist([{"doc_id": "dsid_a", "source_type": "confluence", "title": "t", "content": "c"}]), path)
        documents = {}
        prefetch = candidate_prefetcher({"qst_0001": ["dsid_a"]}, documents, path)
        prefetch(["qst_0001"])
        path.unlink()
        prefetch(["qst_0001"])  # everything cached: no scan, so the missing file is never opened
        self.assertEqual(documents, {"dsid_a": ("t", "c")})

    def test_candidate_ids_are_the_distinct_documents_of_each_saved_question_in_rank_order(self):
        path = Path(self.folder.name) / "candidates.jsonl"
        path.write_text(json.dumps({"question_id": "qst_0001", "question": "q", "candidates": [
            {"node_id": "n1", "ref_doc_id": "dsid_a", "text": "t"}, {"node_id": "n2", "ref_doc_id": "dsid_b", "text": "t"},
            {"node_id": "n3", "ref_doc_id": "dsid_a", "text": "t"}]}) + "\n")
        self.assertEqual(candidate_ids(path), {"qst_0001": ["dsid_a", "dsid_b"]})

    def test_doctests(self):
        self.assertEqual(doctest.testmod(agent_run_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

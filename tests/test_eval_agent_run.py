"""RET-10d-a: usage_of, candidate_ids, candidate_prefetcher, finished_rows, the runner's helpers.

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
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import agent_run as agent_run_module  # noqa: E402
from pipeline.eval.agent_run import candidate_ids, candidate_prefetcher, finished_rows, usage_of  # noqa: E402


class RunHelpers(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_finished_rows_drops_a_last_line_cut_by_a_crash_and_rewrites_the_file(self):
        out = self.path / "answers.jsonl"
        out.write_text('{"question_id": "qst_0001", "answer": "a"}\n{"question_id": "qst_00')
        self.assertEqual(finished_rows(out), [{"question_id": "qst_0001", "answer": "a"}])
        self.assertEqual(out.read_text(), '{"question_id": "qst_0001", "answer": "a"}\n')
        self.assertEqual(finished_rows(self.path / "missing.jsonl"), [])

    def test_usage_is_summed_from_raw_responses_with_cached_tokens_and_zero_without_them(self):
        raw = {"usage": SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=300, cache_creation_input_tokens=0)}
        self.assertEqual(usage_of(raw), (1500, 80))
        self.assertEqual(usage_of(None), (0, 0))
        self.assertEqual(usage_of({"usage": {"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": None}}), (5, 7))

    def test_candidate_ids_are_the_distinct_documents_of_each_saved_question_in_rank_order(self):
        path = self.path / "candidates.jsonl"
        path.write_text(json.dumps({"question_id": "qst_0001", "question": "q", "candidates": [
            {"node_id": "n1", "ref_doc_id": "dsid_a", "text": "t"}, {"node_id": "n2", "ref_doc_id": "dsid_b", "text": "t"},
            {"node_id": "n3", "ref_doc_id": "dsid_a", "text": "t"}]}) + "\n")
        self.assertEqual(candidate_ids(path), {"qst_0001": ["dsid_a", "dsid_b"]})

    def test_the_prefetcher_scans_once_per_batch_and_skips_documents_already_cached(self):
        path = self.path / "documents.parquet"
        pq.write_table(pa.Table.from_pylist([{"doc_id": "dsid_a", "source_type": "confluence", "title": "t", "content": "c"}]), path)
        documents = {}
        prefetch = candidate_prefetcher({"qst_0001": ["dsid_a"]}, documents, path)
        prefetch(["qst_0001"])
        path.unlink()
        prefetch(["qst_0001"])  # everything cached: no scan, so the missing file is never opened
        self.assertEqual(documents, {"dsid_a": ("t", "c")})

    def test_doctests(self):
        self.assertEqual(doctest.testmod(agent_run_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

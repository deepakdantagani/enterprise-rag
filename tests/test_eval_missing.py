"""GEN-4: save_query_vectors and save_candidates, v4's retrieval for the 30 questions never saved.

Run: uv run python -m unittest tests.test_eval_missing
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core import MockEmbedding  # noqa: E402

from pipeline.eval import missing  # noqa: E402
from pipeline.eval.missing import save_candidates, save_query_vectors  # noqa: E402
from pipeline.eval.questions import Question  # noqa: E402
from pipeline.eval.rerank import ReplayRetriever  # noqa: E402

RERANK = ROOT / "data/_index/rerank"
CANDIDATES = RERANK / "lite_titles_top100_candidates.jsonl"
V4_ORDER = RERANK / "lite-titles-top100-rerank-3-lite.jsonl"
QUESTIONS = [Question("q1", "simple", (), "Who?", ()), Question("q2", "info_not_found", (), "When?", ())]
SAVED = {"question_id": "x", "question": "When?", "candidates": [{"node_id": "c1", "ref_doc_id": "dsid_5", "text": "chunk"}]}


def file_holding(*rows):
    path = Path(tempfile.mkdtemp()) / "saved.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def rows_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class SaveCandidates(unittest.TestCase):
    def test_appends_only_the_questions_not_saved_in_the_saved_row_format(self):
        out = file_holding({"question_id": "q1", "question": "Who?", "candidates": []})
        self.assertEqual(save_candidates(ReplayRetriever({"When?": SAVED}), QUESTIONS, out), 1)
        self.assertEqual(rows_of(out)[1], {"question_id": "q2", "question": "When?", "candidates": SAVED["candidates"]})


class SaveQueryVectors(unittest.TestCase):
    def test_appends_only_the_questions_not_saved_as_query_vectors(self):
        out = file_holding({"question_id": "q1", "text": "Who?", "model": "voyage-4", "input_type": "query",
                            "embedding": [0.1]})
        self.assertEqual(save_query_vectors(MockEmbedding(embed_dim=2), "voyage-4", QUESTIONS, out), 1)
        self.assertEqual(rows_of(out)[1], {"question_id": "q2", "text": "When?", "model": "voyage-4",
                                           "input_type": "query", "embedding": [0.5, 0.5]})


@unittest.skipUnless(CANDIDATES.is_file() and V4_ORDER.is_file(), "saved v4 candidates absent")
class RealFiles(unittest.TestCase):
    def test_all_500_questions_are_saved_in_the_same_order_in_both_files(self):
        ids = [[row["question_id"] for row in rows_of(path)] for path in (CANDIDATES, V4_ORDER)]
        self.assertEqual((len(ids[0]), len(set(ids[0])), ids[0] == ids[1]), (500, 500, True))


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(missing).failed, 0)


if __name__ == "__main__":
    unittest.main()

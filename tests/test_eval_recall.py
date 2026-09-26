"""EVAL-1: document_recall, the leaderboard's document recall over the first k distinct documents.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import recall as recall_module  # noqa: E402
from pipeline.eval.recall import document_recall  # noqa: E402


class DocumentRecall(unittest.TestCase):
    def test_expected_doc_retrieved_scores_one(self):
        self.assertEqual(document_recall(["a", "b"], ["a"], k=10), 1.0)

    def test_chunks_of_one_document_take_one_place(self):
        self.assertEqual(document_recall(["a", "a", "a", "b"], ["b"], k=2), 1.0)

    def test_document_past_k_does_not_count(self):
        self.assertEqual(document_recall(["a", "b", "c"], ["c"], k=2), 0.0)

    def test_half_of_two_expected_docs_scores_half(self):
        self.assertEqual(document_recall(["a"], ["a", "b"]), 0.5)

    def test_question_with_no_expected_docs_is_not_scored(self):
        self.assertIsNone(document_recall(["a"], []))

    def test_nothing_retrieved_scores_zero(self):
        self.assertEqual(document_recall([], ["a"]), 0.0)

    def test_k_must_be_positive(self):
        with self.assertRaises(ValueError):
            document_recall(["a"], ["a"], k=0)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(recall_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

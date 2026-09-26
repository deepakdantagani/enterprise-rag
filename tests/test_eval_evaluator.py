"""EVAL-1: DocumentRetrieverEvaluator, LlamaIndex's RetrieverEvaluator scored on documents, not chunks.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import evaluator as evaluator_module  # noqa: E402
from pipeline.eval.evaluator import DocumentRetrieverEvaluator  # noqa: E402

METRICS = ["hit_rate", "recall", "mrr", "ndcg"]


class ChunksOf(BaseRetriever):
    """A retriever that returns one chunk per listed document id, in that order."""

    def __init__(self, doc_ids):
        super().__init__()
        self.doc_ids = doc_ids

    def _retrieve(self, query_bundle):
        return [NodeWithScore(node=TextNode(text=f"chunk {rank} of {doc_id}",
                                            relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)}),
                              score=1.0 - rank / 100)
                for rank, doc_id in enumerate(self.doc_ids)]


def evaluate(ranked_doc_ids, expected_doc_ids, top_k_docs=10):
    evaluator = DocumentRetrieverEvaluator.from_metric_names(METRICS, retriever=ChunksOf(ranked_doc_ids), top_k_docs=top_k_docs)
    return evaluator.evaluate("any question", expected_ids=expected_doc_ids)


class DocumentRetrieverEvaluatorTest(unittest.TestCase):
    def test_retrieved_ids_are_documents_in_rank_order_without_repeats(self):
        self.assertEqual(evaluate(["a", "a", "a", "b"], ["b"], top_k_docs=2).retrieved_ids, ["a", "b"])

    def test_chunks_of_one_document_take_one_place(self):
        self.assertEqual(evaluate(["a", "a", "a", "b"], ["b"], top_k_docs=2).metric_vals_dict["recall"], 1.0)

    def test_document_past_top_k_does_not_count(self):
        self.assertEqual(evaluate(["a", "b", "c"], ["c"], top_k_docs=2).metric_vals_dict["recall"], 0.0)

    def test_half_of_two_expected_docs_is_recall_one_half(self):
        self.assertEqual(evaluate(["a"], ["a", "b"]).metric_vals_dict["recall"], 0.5)

    def test_mrr_counts_document_rank_not_chunk_rank(self):
        # b is the 4th chunk but the 2nd document
        self.assertEqual(evaluate(["a", "a", "a", "b"], ["b"]).metric_vals_dict["mrr"], 0.5)

    def test_retrieved_text_is_the_documents_best_chunk(self):
        self.assertEqual(evaluate(["a", "b", "a"], ["a"]).retrieved_texts, ["chunk 0 of a", "chunk 1 of b"])

    def test_top_k_docs_must_be_positive(self):
        with self.assertRaises(ValidationError):
            DocumentRetrieverEvaluator.from_metric_names(METRICS, retriever=ChunksOf(["a"]), top_k_docs=0)

    def test_chunk_without_a_source_document_is_an_error(self):
        class NoSource(BaseRetriever):
            def _retrieve(self, query_bundle):
                return [NodeWithScore(node=TextNode(id_="orphan", text="x"), score=1.0)]
        evaluator = DocumentRetrieverEvaluator.from_metric_names(METRICS, retriever=NoSource())
        with self.assertRaisesRegex(ValueError, "orphan"):
            evaluator.evaluate("any question", expected_ids=["a"])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(evaluator_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

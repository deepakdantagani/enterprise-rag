"""EVAL-3c: score_retriever, every question at every k, scored in one event loop.

Run: uv run python -m unittest discover tests
"""
import asyncio
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import score as score_module  # noqa: E402
from pipeline.eval.questions import Question  # noqa: E402
from pipeline.eval.score import score_retriever  # noqa: E402

ROLLBACK = Question("qst_0431", "completeness", ("confluence",), "Emergency rollback?", ("dsid_a", "dsid_z"))
METRIC = Question("qst_0002", "basic", ("github",), "Which metric?", ("dsid_b",))


def chunk_of(doc_id, rank):
    return NodeWithScore(node=TextNode(text=f"chunk {rank} of {doc_id}",
                                       relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)}),
                         score=1.0 - rank / 100)


class RanksAThenB(BaseRetriever):
    def _retrieve(self, query_bundle):
        return [chunk_of(doc_id, rank) for rank, doc_id in enumerate(["dsid_a", "dsid_x", "dsid_y", "dsid_b"])]


class BoundToFirstLoop(RanksAThenB):
    """Like Qdrant's async client: fails when called from a different event loop than the first."""

    def __init__(self):
        super().__init__()
        self.loop = None

    async def _aretrieve(self, query_bundle):
        self.loop = self.loop or asyncio.get_running_loop()
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Event loop is closed")
        return self._retrieve(query_bundle)


class ScoreRetriever(unittest.TestCase):
    def test_one_result_per_question_and_k_in_order(self):
        scored = score_retriever(RanksAThenB(), [ROLLBACK, METRIC], ks=(2, 10))
        self.assertEqual([(one.question.question_id, one.k) for one in scored],
                         [("qst_0431", 2), ("qst_0431", 10), ("qst_0002", 2), ("qst_0002", 10)])

    def test_metrics_are_computed_on_the_top_k_documents(self):
        scored = score_retriever(RanksAThenB(), [ROLLBACK, METRIC], ks=(2, 10))
        self.assertEqual([one.metrics["recall"] for one in scored], [0.5, 0.5, 0.0, 1.0])
        self.assertEqual(scored[3].metrics["mrr"], 0.25)

    def test_every_question_runs_in_the_same_event_loop(self):
        scored = score_retriever(BoundToFirstLoop(), [ROLLBACK, METRIC], ks=(5, 10, 20))
        self.assertEqual(len(scored), 6)

    def test_reports_all_five_metrics(self):
        [one] = score_retriever(RanksAThenB(), [METRIC], ks=(10,))
        self.assertEqual(sorted(one.metrics), ["hit_rate", "mrr", "ndcg", "precision", "recall"])

    def test_precision_is_relevant_documents_over_documents_returned(self):
        scored = score_retriever(RanksAThenB(), [ROLLBACK, METRIC], ks=(2, 10))
        self.assertEqual([one.metrics["precision"] for one in scored], [0.5, 0.25, 0.0, 0.25])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(score_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

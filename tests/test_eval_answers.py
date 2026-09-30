import doctest
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode  # noqa: E402

from pipeline.eval import answers  # noqa: E402
from pipeline.eval.answers import document_block, first_documents  # noqa: E402

RERANK = ROOT / "data/_index/rerank"
CANDIDATES = RERANK / "lite_titles_top100_candidates.jsonl"
V4_ORDER = RERANK / "lite-titles-top100-rerank-3-lite.jsonl"


def chunk_of(doc_id):
    return NodeWithScore(node=TextNode(text="chunk", relationships={
        NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)}), score=1.0)


class FirstDocuments(unittest.TestCase):
    def test_keeps_the_first_ten_distinct_documents_in_rank_order(self):
        ranked = [chunk_of(f"dsid_{n}") for n in [3, 3, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]]
        self.assertEqual(first_documents(ranked), ["dsid_3", "dsid_0", "dsid_1", "dsid_2", "dsid_4",
                                                   "dsid_5", "dsid_6", "dsid_7", "dsid_8", "dsid_9"])

    def test_a_document_ranks_where_its_best_chunk_ranks(self):
        ranked = [chunk_of("dsid_b"), chunk_of("dsid_a"), chunk_of("dsid_b"), chunk_of("dsid_a")]
        self.assertEqual(first_documents(ranked), ["dsid_b", "dsid_a"])

    def test_fewer_documents_than_ten_keeps_them_all(self):
        self.assertEqual(first_documents([chunk_of("dsid_1"), chunk_of("dsid_2")]), ["dsid_1", "dsid_2"])

    def test_no_chunks_gives_no_documents(self):
        self.assertEqual(first_documents([]), [])


class DocumentBlock(unittest.TestCase):
    def test_the_benchmark_baseline_layout(self):
        self.assertEqual(document_block(2, "dsid_a", "Q3 budget", "Priya approved it."),
                         "--- Document 2 (ID: dsid_a) ---\nTitle: Q3 budget\n\nPriya approved it.")


@unittest.skipUnless(CANDIDATES.is_file() and V4_ORDER.is_file(), "saved v4 reranks absent")
class RealTopTen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.eval.rerank import replay_retriever
        cls.retriever = replay_retriever(CANDIDATES, V4_ORDER)
        cls.questions = [json.loads(line)["question"] for line in CANDIDATES.read_text().splitlines()]

    def test_qst_0001_gets_ten_documents_with_its_gold_document_first(self):
        doc_ids = first_documents(self.retriever.retrieve(self.questions[0]))
        self.assertEqual((len(doc_ids), doc_ids[0]), (10, "dsid_ae068ee4aa9640159427cd941bef0238"))

    def test_every_saved_question_reaches_ten_documents(self):
        counts = [len(first_documents(self.retriever.retrieve(question))) for question in self.questions]
        self.assertEqual((len(counts), set(counts)), (470, {10}))


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(answers).failed, 0)


if __name__ == "__main__":
    unittest.main()

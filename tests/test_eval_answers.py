import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core.schema import MetadataMode, NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode  # noqa: E402

from pipeline.eval import answers  # noqa: E402
from pipeline.eval.answers import FullDocuments, document_block, documents_by_id, first_documents  # noqa: E402

CORPUS = ROOT / "data/_full/documents.parquet"
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


def parquet_of(rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    folder = tempfile.mkdtemp()
    path = Path(folder) / "documents.parquet"
    pq.write_table(pa.Table.from_pylist([{"doc_id": d, "title": t, "content": c} for d, t, c in rows]), path)
    return path


class DocumentsById(unittest.TestCase):
    def test_returns_only_the_asked_documents(self):
        path = parquet_of([("a", "A", "about a"), ("b", "B", "about b"), ("c", "C", "about c")])
        self.assertEqual(documents_by_id(path, ["a", "c"]), {"a": ("A", "about a"), "c": ("C", "about c")})

    def test_titles_lose_surrounding_spaces(self):
        self.assertEqual(documents_by_id(parquet_of([("a", "  A  ", "about a")]), ["a"]), {"a": ("A", "about a")})

    def test_an_id_used_by_two_documents_shows_both_texts(self):
        path = parquet_of([("a", "First", "one"), ("a", "Second", "two")])
        self.assertEqual(documents_by_id(path, ["a"]), {"a": ("First", "one\n\nSecond\n\ntwo")})

    def test_an_unknown_id_is_left_out(self):
        self.assertEqual(documents_by_id(parquet_of([("a", "A", "about a")]), ["zzz"]), {})


DOCUMENTS = {"dsid_2": ("Title 2", "Content 2"), "dsid_5": ("Title 5", "Content 5")}


class FullDocumentsPostprocessor(unittest.TestCase):
    def setUp(self):
        self.kept = FullDocuments(DOCUMENTS).postprocess_nodes([chunk_of("dsid_5"), chunk_of("dsid_5"), chunk_of("dsid_2")])

    def test_each_document_becomes_one_numbered_node_with_its_whole_text(self):
        self.assertEqual([found.node.text for found in self.kept],
                         ["--- Document 1 (ID: dsid_5) ---\nTitle: Title 5\n\nContent 5",
                          "--- Document 2 (ID: dsid_2) ---\nTitle: Title 2\n\nContent 2"])

    def test_each_node_is_its_document_id_and_keeps_it_in_metadata(self):
        self.assertEqual([(found.node.node_id, found.node.metadata["doc_id"]) for found in self.kept],
                         [("dsid_5", "dsid_5"), ("dsid_2", "dsid_2")])

    def test_the_llm_sees_the_block_without_a_doc_id_line(self):
        self.assertEqual(self.kept[0].node.get_content(metadata_mode=MetadataMode.LLM),
                         "--- Document 1 (ID: dsid_5) ---\nTitle: Title 5\n\nContent 5")

    def test_a_document_that_was_not_loaded_fails_loudly(self):
        with self.assertRaises(KeyError):
            FullDocuments(DOCUMENTS).postprocess_nodes([chunk_of("dsid_missing")])


@unittest.skipUnless(CORPUS.is_file() and CANDIDATES.is_file() and V4_ORDER.is_file(), "corpus or saved v4 reranks absent")
class RealFullDocuments(unittest.TestCase):
    def test_qst_0009_gets_the_whole_edgepath_thread_first(self):
        from pipeline.eval.rerank import replay_retriever
        chunks = replay_retriever(CANDIDATES, V4_ORDER).retrieve(
            "In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
            "instead of matching the competitor's 50 percent first-year discount and migration credit?")
        kept = FullDocuments(documents_by_id(CORPUS, first_documents(chunks))).postprocess_nodes(chunks)
        self.assertEqual((len(kept), kept[0].node.node_id), (10, "dsid_85deb10a652742baaf28af6149600001"))
        self.assertIn("CloudOrbit (the incumbent) is offering a 50% discount", kept[0].node.text)


@unittest.skipUnless(CORPUS.is_file(), "corpus absent")
class RealDocuments(unittest.TestCase):
    def test_the_gold_document_of_qst_0001_is_read_whole(self):
        title, content = documents_by_id(CORPUS, ["dsid_ae068ee4aa9640159427cd941bef0238"])[
            "dsid_ae068ee4aa9640159427cd941bef0238"]
        self.assertTrue(title.startswith("add multipart/form-data handling"))
        self.assertEqual(len(content), 5120)

    def test_the_signal_peak_id_shows_both_of_its_documents(self):
        title, content = documents_by_id(CORPUS, ["dsid_8a0c5430bac64f8da21c2cee5a7f4df5"])[
            "dsid_8a0c5430bac64f8da21c2cee5a7f4df5"]
        self.assertEqual(title, "Signal Peak Logistics — Account Brief (Renewal + Expansion) — 2026-03-18")
        self.assertEqual(len(content), 1534 + len("\n\nSignal Peak Logistics\n\n") + 3645)


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

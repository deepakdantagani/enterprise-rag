"""EVAL-3d1: embedded_doc_ids, the dsids already in the Qdrant collection, so a re-run skips them.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
import warnings
from pathlib import Path

from llama_index.core import Document, MockEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import resume as resume_module  # noqa: E402
from pipeline.eval.resume import embedded_doc_ids  # noqa: E402

LONG_PAGE = Document(id_="dsid_a", text="Roll back the release in every region. " * 150)
SHORT_PAGE = Document(id_="dsid_b", text="Pin the previous runtime version.")


def qdrant_with(documents):
    client = QdrantClient(":memory:")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "payload indexes have no effect in the local Qdrant"
        IngestionPipeline(transformations=[SentenceSplitter(chunk_size=512, chunk_overlap=50), MockEmbedding(embed_dim=8)],
                          vector_store=QdrantVectorStore(client=client, collection_name="baseline")).run(documents=documents)
    return client


class EmbeddedDocIds(unittest.TestCase):
    def test_every_embedded_document_once_however_many_chunks(self):
        self.assertEqual(embedded_doc_ids(qdrant_with([LONG_PAGE, SHORT_PAGE]), "baseline"), {"dsid_a", "dsid_b"})

    def test_reads_past_one_page_of_chunks(self):
        client = qdrant_with([LONG_PAGE, SHORT_PAGE])
        self.assertEqual(embedded_doc_ids(client, "baseline", page_size=1), {"dsid_a", "dsid_b"})

    def test_a_collection_not_created_yet_has_nothing_embedded(self):
        self.assertEqual(embedded_doc_ids(QdrantClient(":memory:"), "baseline"), set())

    def test_doctests(self):
        self.assertEqual(doctest.testmod(resume_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

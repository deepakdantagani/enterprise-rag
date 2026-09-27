"""RET-1: copy_to_hybrid, every v0 chunk into a hybrid collection with its dense vector unchanged plus BM25.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
import warnings
from pathlib import Path

from llama_index.core.schema import TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import hybrid as hybrid_module  # noqa: E402
from pipeline.eval.hybrid import copy_to_hybrid, hybrid_store  # noqa: E402

QDRANT_URL = "http://localhost:6333"
RUNBOOK_CHUNK = "0e9ae45d-cb1e-4c5c-ad98-f5e090a0c7a9"  # first chunk of the perf-canary runbook in v0

NODES = [TextNode(id_=f"00000000-0000-0000-0000-00000000000{n}", text=text, embedding=[0.1 * n, 0.2, 0.3, 0.4],
                  metadata={"source_type": "slack"})
         for n, text in enumerate(["Roll back the perf-canary release.", "Priya approved the Q3 budget.",
                                   "The Berlin office moved."], start=1)]


def source_with(nodes):
    client = QdrantClient(":memory:")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "payload indexes have no effect in the local Qdrant"
        QdrantVectorStore(client=client, collection_name="v0").add(nodes)
    return client


def point(client, collection, point_id):
    [found] = client.retrieve(collection, [point_id], with_payload=True, with_vectors=True)
    return found


class CopyToHybrid(unittest.TestCase):
    def setUp(self):
        self.client = source_with(NODES)
        self.store = hybrid_store(self.client, "hybrid")

    def test_every_chunk_is_copied_with_its_id_payload_and_dense_vector_unchanged(self):
        self.assertEqual(copy_to_hybrid(self.client, "v0", self.store, page_size=2), 3)
        for node in NODES:
            before, after = point(self.client, "v0", node.node_id), point(self.client, "hybrid", node.node_id)
            self.assertEqual(after.payload, before.payload)
            self.assertEqual(after.vector["text-dense"], before.vector)

    def test_every_chunk_gets_a_bm25_vector_of_its_own_words(self):
        copy_to_hybrid(self.client, "v0", self.store)
        sparse = [point(self.client, "hybrid", node.node_id).vector["text-sparse-new"] for node in NODES]
        self.assertTrue(all(vector.indices for vector in sparse))
        self.assertEqual(len({tuple(vector.indices) for vector in sparse}), 3)

    def test_the_sparse_vector_uses_qdrants_idf(self):
        copy_to_hybrid(self.client, "v0", self.store)
        [config] = self.client.get_collection("hybrid").config.params.sparse_vectors.values()
        self.assertEqual(config.modifier, "idf")

    def test_a_rerun_copies_nothing_new(self):
        copy_to_hybrid(self.client, "v0", self.store)
        self.assertEqual(copy_to_hybrid(self.client, "v0", self.store, page_size=2), 0)
        self.assertEqual(self.client.count("hybrid").count, 3)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(hybrid_module).failed, 0)


def local_qdrant_has_v0():
    try:
        return QdrantClient(url=QDRANT_URL, timeout=5).collection_exists("baseline__voyage_4")
    except Exception:
        return False


@unittest.skipUnless(local_qdrant_has_v0(), "needs the v0 collection baseline__voyage_4 in a local Qdrant")
class RealRunbookChunk(unittest.TestCase):
    def test_the_runbook_chunk_gets_157_bm25_words_led_by_canary(self):
        server = QdrantClient(url=QDRANT_URL)
        [chunk] = server.retrieve("baseline__voyage_4", [RUNBOOK_CHUNK], with_payload=True, with_vectors=True)
        client = QdrantClient(":memory:")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            client.create_collection("v0", vectors_config=server.get_collection("baseline__voyage_4").config.params.vectors)
        client.upsert("v0", [PointStruct(id=chunk.id, vector=chunk.vector, payload=chunk.payload)])
        copy_to_hybrid(client, "v0", hybrid_store(client, "hybrid"))
        sparse = point(client, "hybrid", RUNBOOK_CHUNK).vector["text-sparse-new"]
        self.assertEqual(len(sparse.indices), 157)
        self.assertEqual(round(max(sparse.values), 3), 1.986)  # 'canari': 11 times in the chunk


if __name__ == "__main__":
    unittest.main()

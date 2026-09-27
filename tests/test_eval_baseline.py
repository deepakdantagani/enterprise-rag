"""EVAL-3b: baseline_pipeline, the naive baseline as one LlamaIndex IngestionPipeline.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.core import Document, MockEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores import SimpleVectorStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import baseline as baseline_module  # noqa: E402
from pipeline.eval.baseline import baseline_pipeline  # noqa: E402

LONG_PAGE = Document(id_="dsid_a", text="Roll back the release in every region. " * 150)
SHORT_PAGE = Document(id_="dsid_b", text="Pin the previous runtime version.")


class CountingEmbedding(MockEmbedding):
    texts_embedded: int = 0

    def _get_text_embeddings(self, texts):
        self.texts_embedded += len(texts)
        return super()._get_text_embeddings(texts)


def pipeline_with(embed_model):
    return baseline_pipeline(embed_model, SimpleVectorStore(), SimpleDocumentStore())


class BaselinePipeline(unittest.TestCase):
    def test_splits_with_sentence_splitter_512_overlap_50(self):
        splitter = pipeline_with(MockEmbedding(embed_dim=8)).transformations[0]
        self.assertIsInstance(splitter, SentenceSplitter)
        self.assertEqual((splitter.chunk_size, splitter.chunk_overlap), (512, 50))

    def test_every_chunk_is_embedded_and_keeps_its_dsid(self):
        chunks = pipeline_with(MockEmbedding(embed_dim=8)).run(documents=[LONG_PAGE, SHORT_PAGE])
        self.assertGreater(len(chunks), 2)
        self.assertEqual({chunk.ref_doc_id for chunk in chunks}, {"dsid_a", "dsid_b"})
        self.assertTrue(all(len(chunk.embedding) == 8 for chunk in chunks))

    def test_chunks_land_in_the_vector_store(self):
        pipeline = pipeline_with(MockEmbedding(embed_dim=8))
        chunks = pipeline.run(documents=[LONG_PAGE, SHORT_PAGE])
        self.assertEqual(len(pipeline.vector_store.data.embedding_dict), len(chunks))

    def test_a_rerun_embeds_nothing_already_embedded(self):
        embed_model = CountingEmbedding(embed_dim=8)
        pipeline = pipeline_with(embed_model)
        pipeline.run(documents=[LONG_PAGE, SHORT_PAGE])
        embedded_once = embed_model.texts_embedded
        self.assertEqual(pipeline.run(documents=[LONG_PAGE, SHORT_PAGE]), [])
        self.assertEqual(embed_model.texts_embedded, embedded_once)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(baseline_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

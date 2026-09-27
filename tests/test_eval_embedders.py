"""EVAL-3f: embed_model_named and collection_name, one baseline command for each embedder.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.embeddings.voyageai import VoyageEmbedding

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import embedders as embedders_module  # noqa: E402
from pipeline.eval.embedders import EMBEDDERS, collection_name, embed_model_named  # noqa: E402


class EmbedModelNamed(unittest.TestCase):
    def test_voyage_4_runs_on_the_voyage_api_at_1024_dimensions(self):
        model = embed_model_named("voyage-4", voyage_api_key="not-a-real-key")
        self.assertIsInstance(model, VoyageEmbedding)
        self.assertEqual((model.model_name, model.output_dimension), ("voyage-4", 1024))

    def test_an_unknown_name_lists_the_known_ones(self):
        with self.assertRaisesRegex(ValueError, "known: voyage-4"):
            embed_model_named("qwen3-embedding:0.6b")

    def test_voyage_4_is_the_only_and_default_embedder(self):
        # the local qwen3-embedding:0.6b path was removed: ~20 h for the full corpus on this Mac
        self.assertEqual(list(EMBEDDERS), ["voyage-4"])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(embedders_module).failed, 0)


class CollectionName(unittest.TestCase):
    def test_each_embedder_and_corpus_gets_its_own_collection(self):
        self.assertEqual(collection_name("voyage-4", sample=True), "baseline_sample__voyage_4")
        self.assertEqual(collection_name("voyage-4", sample=False), "baseline__voyage_4")


if __name__ == "__main__":
    unittest.main()

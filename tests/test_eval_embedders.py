"""EVAL-3f: embed_model_named and collection_name, one baseline command for each embedder.

Run: uv run python -m unittest discover tests
"""
import asyncio
import doctest
import json
import tempfile
import sys
import unittest
from pathlib import Path

from llama_index.core import MockEmbedding
from llama_index.embeddings.voyageai import VoyageEmbedding

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import embedders as embedders_module  # noqa: E402
from pipeline.eval.embedders import EMBEDDERS, collection_name, embed_model_named, saved_query_embeddings  # noqa: E402


class EmbedModelNamed(unittest.TestCase):
    def test_voyage_4_runs_on_the_voyage_api_at_1024_dimensions(self):
        model = embed_model_named("voyage-4", voyage_api_key="not-a-real-key")
        self.assertIsInstance(model, VoyageEmbedding)
        self.assertEqual((model.model_name, model.output_dimension), ("voyage-4", 1024))

    def test_an_unknown_name_lists_the_known_ones(self):
        with self.assertRaisesRegex(ValueError, "known: voyage-4-lite, voyage-4"):
            embed_model_named("qwen3-embedding:0.6b")

    def test_voyage_4_lite_is_the_default_and_voyage_4_the_other_embedder(self):
        # EVAL-3l: lite is the base (0.834 vs 0.845, within noise, a third of the cost);
        # the local qwen3-embedding:0.6b path was removed: ~20 h for the full corpus on this Mac
        self.assertEqual(list(EMBEDDERS), ["voyage-4-lite", "voyage-4"])

    def test_voyage_4_lite_also_gives_1024_dimensions_in_the_shared_space(self):
        model = embed_model_named("voyage-4-lite", voyage_api_key="not-a-real-key")
        self.assertEqual((model.model_name, model.output_dimension), ("voyage-4-lite", 1024))

    def test_doctests(self):
        self.assertEqual(doctest.testmod(embedders_module).failed, 0)


class CollectionName(unittest.TestCase):
    def test_each_embedder_and_corpus_gets_its_own_collection(self):
        self.assertEqual(collection_name("voyage-4", sample=True), "baseline_sample__voyage_4")
        self.assertEqual(collection_name("voyage-4", sample=False), "baseline__voyage_4")


SAVED = ROOT / "data/_index/question_embeddings/voyage-4.jsonl"


class CountingVoyage(MockEmbedding):
    """Stands in for Voyage: returns a fixed vector and counts the calls that would have cost money."""
    calls: int = 0

    def _get_query_embedding(self, query):
        self.calls += 1
        return [9.0, 9.0]

    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)


def saved_file(rows):
    path = Path(tempfile.mkdtemp()) / "voyage-4.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


ROWS = [{"question_id": "qst_0017", "text": "What service credit percentages were proposed?", "model": "voyage-4",
         "input_type": "query", "embedding": [0.1, 0.2]}]


class SavedQueryEmbeddings(unittest.TestCase):
    def test_a_saved_question_gets_its_saved_vector_without_calling_voyage(self):
        voyage = CountingVoyage(embed_dim=2)
        model = saved_query_embeddings(saved_file(ROWS), fallback=voyage)
        self.assertEqual(model.get_query_embedding("What service credit percentages were proposed?"), [0.1, 0.2])
        self.assertEqual(voyage.calls, 0)

    def test_the_async_path_used_by_the_scorer_also_reads_the_saved_vector(self):
        voyage = CountingVoyage(embed_dim=2)
        model = saved_query_embeddings(saved_file(ROWS), fallback=voyage)
        vector = asyncio.run(model.aget_query_embedding("What service credit percentages were proposed?"))
        self.assertEqual((vector, voyage.calls), ([0.1, 0.2], 0))

    def test_a_new_question_falls_back_to_voyage(self):
        voyage = CountingVoyage(embed_dim=2)
        model = saved_query_embeddings(saved_file(ROWS), fallback=voyage)
        self.assertEqual(model.get_query_embedding("A question nobody saved?"), [9.0, 9.0])
        self.assertEqual(voyage.calls, 1)

    def test_a_new_question_without_a_fallback_names_the_question(self):
        model = saved_query_embeddings(saved_file(ROWS))
        with self.assertRaisesRegex(KeyError, "A question nobody saved"):
            model.get_query_embedding("A question nobody saved?")

    @unittest.skipUnless(SAVED.is_file(), "needs data/_index/question_embeddings/voyage-4.jsonl")
    def test_the_real_file_holds_470_voyage_4_vectors_of_1024(self):
        model = saved_query_embeddings(SAVED)
        vector = model.get_query_embedding("What service credit percentages were proposed in the tiered uptime SLA "
                                           "counteroffer for the maritime logistics SaaS customer using dedicated "
                                           "GPU capacity?")
        self.assertEqual((model.saved_count, len(vector)), (470, 1024))


if __name__ == "__main__":
    unittest.main()

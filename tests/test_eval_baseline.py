"""EVAL-3b: baseline_pipeline, the naive baseline as one LlamaIndex IngestionPipeline.
EVAL-3d3: ingest_corpus, the corpus through that pipeline batch by batch.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from llama_index.core import Document, MockEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores import SimpleVectorStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import baseline as baseline_module  # noqa: E402
from pipeline.eval.baseline import baseline_pipeline, ingest_corpus  # noqa: E402
from pipeline.observability import events_logged_to  # noqa: E402

LONG_PAGE = Document(id_="dsid_a", text="Roll back the release in every region. " * 150)
SHORT_PAGE = Document(id_="dsid_b", text="Pin the previous runtime version.")


class CountingEmbedding(MockEmbedding):
    texts_embedded: int = 0

    def _get_text_embeddings(self, texts):
        self.texts_embedded += len(texts)
        return super()._get_text_embeddings(texts)


class RecordingEmbedding(MockEmbedding):
    texts: list = []

    def _get_text_embeddings(self, texts):
        self.texts = self.texts + list(texts)
        return super()._get_text_embeddings(texts)


def pipeline_with(embed_model):
    return baseline_pipeline(embed_model, SimpleVectorStore(), SimpleDocumentStore())


ROWS = [{"doc_id": f"dsid_{n}", "source_type": "confluence", "title": f"page {n}",
         "content": f"Runbook {n}: roll back region {n}. " * (40 if n == 0 else 1)} for n in range(5)]


def ingest_five_pages(**options):
    folder = Path(tempfile.mkdtemp())
    pq.write_table(pa.Table.from_pylist(ROWS), folder / "documents.parquet")
    vector_store = SimpleVectorStore()
    with events_logged_to(folder / "events.jsonl"):
        count = ingest_corpus(folder / "documents.parquet", vector_store, MockEmbedding(embed_dim=8), batch_size=2, **options)
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    embedded = {vector_store.data.text_id_to_ref_doc_id[chunk_id] for chunk_id in vector_store.data.embedding_dict}
    return count, embedded, [event for event in events if event["event"] == "StageDone"]


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

    def test_ingest_embeds_every_document_and_counts_them(self):
        count, embedded, _ = ingest_five_pages()
        self.assertEqual((count, embedded), (5, {f"dsid_{n}" for n in range(5)}))

    def test_ingest_skips_documents_already_embedded(self):
        _, embedded, _ = ingest_five_pages(skip_doc_ids={"dsid_1", "dsid_2"})
        self.assertEqual(embedded, {"dsid_0", "dsid_3", "dsid_4"})

    def test_ingest_can_keep_only_a_sample(self):
        _, embedded, _ = ingest_five_pages(keep_doc_ids={"dsid_0", "dsid_4"})
        self.assertEqual(embedded, {"dsid_0", "dsid_4"})

    def test_ingest_can_open_each_text_with_its_title(self):
        folder, embed_model = Path(tempfile.mkdtemp()), RecordingEmbedding(embed_dim=8)
        pq.write_table(pa.Table.from_pylist(ROWS[1:3]), folder / "documents.parquet")
        ingest_corpus(folder / "documents.parquet", SimpleVectorStore(), embed_model, with_title=True)
        self.assertEqual(embed_model.texts, ["page 1\n\nRunbook 1: roll back region 1.", "page 2\n\nRunbook 2: roll back region 2."])

    def test_ingest_logs_one_stage_done_per_batch(self):
        _, _, batches = ingest_five_pages(skip_doc_ids={"dsid_1"})
        self.assertEqual([(event["stage"], event["files"]) for event in batches],
                         [("embed batch 0", 1), ("embed batch 1", 2), ("embed batch 2", 1)])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(baseline_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

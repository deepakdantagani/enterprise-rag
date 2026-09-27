"""EVAL-3a: parquet_documents, documents.parquet rows as LlamaIndex Documents, in batches, no cleaning.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from llama_index.core.schema import MetadataMode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import documents as documents_module  # noqa: E402
from pipeline.eval.documents import parquet_documents  # noqa: E402

DOCUMENTS = ROOT / "data/_full/documents.parquet"
ROWS = [{"doc_id": f"dsid_{n}", "source_type": "slack", "title": f"title {n}", "content": f"content {n}"} for n in range(5)]


def batches_of(rows, batch_size):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "documents.parquet"
        pq.write_table(pa.Table.from_pylist(rows), path)
        return list(parquet_documents(path, batch_size=batch_size))


class ParquetDocuments(unittest.TestCase):
    def test_rows_come_in_batches_in_file_order(self):
        batches = batches_of(ROWS, batch_size=2)
        self.assertEqual([[doc.id_ for doc in batch] for batch in batches],
                         [["dsid_0", "dsid_1"], ["dsid_2", "dsid_3"], ["dsid_4"]])

    def test_a_row_becomes_a_document_with_the_dsid_as_its_id(self):
        document = batches_of(ROWS[:1], batch_size=10)[0][0]
        self.assertEqual((document.id_, document.text, document.metadata),
                         ("dsid_0", "content 0", {"source_type": "slack", "title": "title 0"}))

    def test_only_the_content_is_embedded(self):
        document = batches_of(ROWS[:1], batch_size=10)[0][0]
        self.assertEqual(document.get_content(MetadataMode.EMBED), "content 0")
        self.assertEqual(document.get_content(MetadataMode.LLM), "content 0")

    def test_a_row_with_blank_content_is_skipped(self):
        rows = [ROWS[0], {**ROWS[1], "content": ""}, {**ROWS[2], "content": " \n "}, ROWS[3]]
        self.assertEqual([[doc.id_ for doc in batch] for batch in batches_of(rows, batch_size=2)],
                         [["dsid_0"], ["dsid_3"]])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(documents_module).failed, 0)


@unittest.skipUnless(DOCUMENTS.is_file(), "needs data/_full/documents.parquet")
class RealDocuments(unittest.TestCase):
    def test_the_first_document_is_the_perf_canary_runbook(self):
        document = next(parquet_documents(DOCUMENTS, batch_size=1))[0]
        self.assertEqual((document.id_, document.metadata["title"]),
                         ("dsid_e54ef48bae78474684a957cf613d47d5", "Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod)"))

    def test_the_one_empty_slack_document_is_skipped(self):
        batch = next(batch for number, batch in enumerate(parquet_documents(DOCUMENTS)) if number == 279)
        self.assertEqual(len(batch), 999)
        self.assertNotIn("dsid_33cbedf0709949fd9416c8c864a86cf2", {doc.id_ for doc in batch})

    def test_the_file_holds_511962_documents(self):
        self.assertEqual(pq.ParquetFile(DOCUMENTS).metadata.num_rows, 511_962)


if __name__ == "__main__":
    unittest.main()

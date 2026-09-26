"""SLACK-9 review fix: thread_documents(clean_dir) reads the clean threads as LlamaIndex
Documents, each tagged with its dsid, before any cache or docstore sees them.

Run: uv run python -m unittest discover tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from llama_index.core.embeddings import MockEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores import SimpleVectorStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack.documents import thread_documents  # noqa: E402
from pipeline.slack.nodes import SlackThreadParser  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
FIXTURES = ROOT / "tests/fixtures/slack_truth"
NOVACARE = "dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-novacare-vra-check.txt"


def folder_with(*names: str) -> Path:
    folder = Path(tempfile.mkdtemp())
    for name in names:
        shutil.copy(FIXTURES / name, folder / name)
    return folder


class ThreadDocuments(unittest.TestCase):
    def test_every_document_is_tagged_with_its_dsid_and_carries_only_its_file_name(self):
        [document] = list(thread_documents(folder_with(NOVACARE)))
        self.assertEqual(document.id_, "a4e702bd03254699b0e7bed0000972ab")
        self.assertEqual(document.metadata, {"file_name": NOVACARE})

    def test_only_thread_files_are_read(self):
        documents = list(thread_documents(FIXTURES))  # also holds expected.json
        self.assertEqual(len(documents), 50)
        self.assertTrue(all(document.metadata["file_name"].startswith("dsid_") for document in documents))

    def test_a_txt_file_that_is_not_a_thread_is_an_error(self):
        folder = folder_with(NOVACARE)
        (folder / "notes.txt").write_text("not a thread\n")
        with self.assertRaisesRegex(ValueError, "notes.txt"):
            list(thread_documents(folder))

    def test_the_same_file_in_another_folder_has_the_same_hash(self):
        [here] = list(thread_documents(folder_with(NOVACARE)))
        [there] = list(thread_documents(folder_with(NOVACARE)))
        self.assertEqual(here.hash, there.hash)


class IngestionTwice(unittest.TestCase):
    def test_a_second_run_stores_no_thread_twice(self):
        folder = folder_with(*sorted(path.name for path in FIXTURES.glob("dsid_*.txt"))[:3])
        pipeline = IngestionPipeline(transformations=[SlackThreadParser(), MockEmbedding(embed_dim=8)],
                                     docstore=SimpleDocumentStore(), vector_store=SimpleVectorStore())
        pipeline.run(documents=list(thread_documents(folder)))
        second = pipeline.run(documents=list(thread_documents(folder)))
        self.assertEqual((len(second), len(pipeline.docstore.docs)), (0, 3))


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_every_clean_thread_is_one_document_and_the_manifest_is_not_one(self):
        ids = {document.id_ for document in thread_documents(CLEAN)}
        self.assertEqual(len(ids), 285_605)


if __name__ == "__main__":
    unittest.main()

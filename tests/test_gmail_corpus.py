"""GMAIL-2: write_clean_corpus(raw_dir, clean_dir) cleans every raw Gmail thread and writes _manifest.json.

Run: uv run python -m unittest discover tests
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail.corpus import write_clean_corpus  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"
GOLDEN = ROOT / "tests/golden/gmail_clean_fingerprint.json"
ESCAPED_THREAD = "Notes\\n\\nFrom: Ana\\n- one\\n- two\\n- three\\n"


def fingerprint(rows: list[dict]) -> str:
    lines = "\n".join(f"{row['file']} {row['clean_sha256']}" for row in rows)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


class WriteCleanCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.clean = self.tmp / "clean"
        self.raw.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_each_raw_thread_becomes_a_clean_thread_and_a_row(self):
        (self.raw / "plain.txt").write_text("Plain  \n\nBody.")
        (self.raw / "escaped.txt").write_text(ESCAPED_THREAD)
        rows = write_clean_corpus(self.raw, self.clean)
        self.assertEqual((self.clean / "plain.txt").read_text(), "Plain\n\nBody.\n")
        self.assertEqual((self.clean / "escaped.txt").read_text(), "Notes\n\nFrom: Ana\n- one\n- two\n- three\n")
        self.assertEqual(json.loads((self.clean / "_manifest.json").read_text()), rows)

    def test_row_has_the_manifest_fields_and_the_escape_flag(self):
        (self.raw / "escaped.txt").write_text(ESCAPED_THREAD)
        (row,) = write_clean_corpus(self.raw, self.clean)
        self.assertEqual(
            sorted(row),
            ["clean_bytes", "clean_lines", "clean_sha256", "file", "raw_bytes", "raw_lines", "raw_sha256", "was_escaped"],
        )
        self.assertTrue(row["was_escaped"])
        self.assertEqual(row["raw_sha256"], hashlib.sha256(ESCAPED_THREAD.encode()).hexdigest())

    def test_rows_are_ordered_by_file_name_and_other_files_are_ignored(self):
        (self.raw / "b.txt").write_text("B\n")
        (self.raw / "a.txt").write_text("A\n")
        (self.raw / "notes.md").write_text("not a thread")
        rows = write_clean_corpus(self.raw, self.clean)
        self.assertEqual([row["file"] for row in rows], ["a.txt", "b.txt"])
        self.assertFalse((self.clean / "notes.md").exists())

    def test_a_carriage_return_is_hashed_as_it_is_on_disk(self):
        raw_bytes = b"Title\r\n\r\nBody\r\n"
        (self.raw / "crlf.txt").write_bytes(raw_bytes)
        (row,) = write_clean_corpus(self.raw, self.clean)
        self.assertEqual(row["raw_sha256"], hashlib.sha256(raw_bytes).hexdigest())
        self.assertEqual((self.clean / "crlf.txt").read_bytes(), b"Title\n\nBody\n")

    def test_raw_folder_is_never_written_to(self):
        (self.raw / "a.txt").write_text("A  \n")
        before = {path.name: path.read_bytes() for path in self.raw.iterdir()}
        write_clean_corpus(self.raw, self.clean)
        self.assertEqual({path.name: path.read_bytes() for path in self.raw.iterdir()}, before)

    def test_a_second_run_gives_identical_rows(self):
        (self.raw / "escaped.txt").write_text(ESCAPED_THREAD)
        first = write_clean_corpus(self.raw, self.clean)
        self.assertEqual(write_clean_corpus(self.raw, self.clean), first)

    def test_empty_folder_gives_empty_manifest(self):
        self.assertEqual(write_clean_corpus(self.raw, self.clean), [])
        self.assertEqual(json.loads((self.clean / "_manifest.json").read_text()), [])

    @unittest.skipUnless(RAW_DIR.is_dir(), "real Gmail corpus not present (data/ is gitignored)")
    def test_real_corpus_matches_golden_fingerprint(self):
        golden = json.loads(GOLDEN.read_text())
        rows = write_clean_corpus(RAW_DIR, self.clean)
        self.assertEqual(len(rows), 121_390)
        self.assertEqual(len(list(self.clean.glob("*.txt"))), 121_390)
        self.assertEqual(sum(row["was_escaped"] for row in rows), 27_870)
        self.assertEqual(fingerprint(rows), golden["fingerprint_sha256"])


if __name__ == "__main__":
    unittest.main()

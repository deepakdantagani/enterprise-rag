"""PARSE-2c: write_clean_corpus(raw_dir, clean_dir) runs 2a over every .txt and writes _manifest.json.

Run: uv run python -m unittest discover tests
"""
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.corpus import write_clean_corpus  # noqa: E402

RAW_DIR = ROOT / "data/confluence/raw"
GOLDEN = ROOT / "tests/golden/corpus_fingerprint.json"


def fingerprint(rows: list[dict]) -> str:
    lines = "\n".join(f"{r['file']} {r['clean_sha256']}" for r in rows)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


class WriteCleanCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.clean = self.tmp / "clean"
        self.raw.mkdir()

    def test_two_raw_files_give_two_clean_files_and_two_rows(self):
        (self.raw / "one.txt").write_text("One\n\nBody.\n")
        (self.raw / "two.txt").write_text("Two   \n\n\n\nBody.\n")
        rows = write_clean_corpus(self.raw, self.clean)
        self.assertEqual((self.clean / "one.txt").read_text(), "One\n\nBody.\n")
        self.assertEqual((self.clean / "two.txt").read_text(), "Two\n\nBody.\n")
        self.assertEqual(json.loads((self.clean / "_manifest.json").read_text()), rows)
        self.assertEqual(len(rows), 2)

    def test_empty_folder_gives_empty_manifest(self):
        rows = write_clean_corpus(self.raw, self.clean)
        self.assertEqual(rows, [])
        self.assertEqual(json.loads((self.clean / "_manifest.json").read_text()), [])

    def test_rows_are_ordered_by_file_name(self):
        (self.raw / "b.txt").write_text("B\n")
        (self.raw / "a.txt").write_text("A\n")
        rows = write_clean_corpus(self.raw, self.clean)
        self.assertEqual([r["file"] for r in rows], ["a.txt", "b.txt"])

    @unittest.skipUnless(RAW_DIR.is_dir(), "real raw corpus not present (data/ is gitignored)")
    def test_real_corpus_matches_golden_fingerprint(self):
        golden = json.loads(GOLDEN.read_text())
        rows = write_clean_corpus(RAW_DIR, self.clean)
        self.assertEqual(len(rows), golden["files"])
        self.assertEqual(sum(r["was_escaped"] for r in rows), golden["escaped"])
        self.assertEqual(fingerprint(rows), golden["fingerprint_sha256"])

    def test_each_raw_file_is_read_exactly_once(self):
        (self.raw / "a.txt").write_text("A\n")
        (self.raw / "b.txt").write_text("B\n")
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=Path.read_text) as read:
            write_clean_corpus(self.raw, self.clean)
        self.assertEqual(sorted(str(c.args[0]) for c in read.call_args_list),
                         sorted(str(self.raw / n) for n in ("a.txt", "b.txt")))


if __name__ == "__main__":
    unittest.main()

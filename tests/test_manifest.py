"""PARSE-2b: manifest_row(name, raw, result) builds one manifest entry, no file IO.

Run: uv run python -m unittest discover tests
"""
import doctest
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.cleaning import CleanResult  # noqa: E402
from pipeline import manifest  # noqa: E402
from pipeline.manifest import manifest_row  # noqa: E402

KEYS = ["file", "raw_sha256", "clean_sha256", "was_escaped",
        "raw_lines", "clean_lines", "raw_bytes", "clean_bytes"]


class ManifestRow(unittest.TestCase):
    def test_row_has_exactly_the_eight_keys(self):
        row = manifest_row("page.txt", "a\nb", CleanResult(text="a\nb\n", was_escaped=False))
        self.assertEqual(list(row), KEYS)

    def test_same_inputs_give_equal_rows(self):
        args = ("page.txt", "a\nb", CleanResult(text="a\nb\n", was_escaped=True))
        self.assertEqual(manifest_row(*args), manifest_row(*args))

    def test_counts_for_raw_without_trailing_newline(self):
        row = manifest_row("page.txt", "a\nb", CleanResult(text="a\nb\n", was_escaped=False))
        self.assertEqual(row["raw_lines"], 2)
        self.assertEqual(row["clean_lines"], 2)
        self.assertEqual(row["raw_bytes"], 3)
        self.assertEqual(row["clean_bytes"], 4)

    def test_fingerprints_and_flag(self):
        row = manifest_row("page.txt", "x\\ny", CleanResult(text="x\ny\n", was_escaped=True))
        self.assertEqual(row["file"], "page.txt")
        self.assertEqual(row["raw_sha256"], hashlib.sha256(b"x\\ny").hexdigest())
        self.assertEqual(row["clean_sha256"], hashlib.sha256(b"x\ny\n").hexdigest())
        self.assertTrue(row["was_escaped"])

    def test_module_touches_no_files(self):
        source = (ROOT / "pipeline/manifest.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"manifest.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(manifest))
    return tests


if __name__ == "__main__":
    unittest.main()

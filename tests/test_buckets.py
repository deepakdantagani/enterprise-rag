"""PARSE-3: bucket(text) says which markup style a clean file uses (pipeline/buckets.py).

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import buckets  # noqa: E402
from pipeline.buckets import bucket  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
V0_COUNTS = {"A_hash": 1645, "B_setext": 781, "C_plain_labels": 2751, "D_prose": 12}


class Bucket(unittest.TestCase):
    def test_hash_heading(self):
        self.assertEqual(bucket("# Title\n\ntext"), "A_hash")

    def test_setext_heading(self):
        self.assertEqual(bucket("Title\n-----\n\ntext"), "B_setext")

    def test_list_without_headings(self):
        self.assertEqual(bucket("Overview\n\n- item"), "C_plain_labels")

    def test_prose_and_empty(self):
        self.assertEqual(bucket("Just prose.\n\nMore prose."), "D_prose")
        self.assertEqual(bucket(""), "D_prose")

    def test_hash_wins_over_setext(self):
        self.assertEqual(bucket("Intro\n-----\n\n# Real\n\n- item"), "A_hash")

    def test_module_is_only_bucket_and_its_regexes(self):
        source = (ROOT / "pipeline/buckets.py").read_text()
        self.assertEqual(source.count("\ndef "), 1)
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"buckets.py must be pure; found {forbidden!r}")

    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_real_corpus_counts_match_v0(self):
        files = sorted(p for p in CLEAN_DIR.glob("*.txt"))
        counts = Counter(bucket(p.read_text(encoding="utf-8")) for p in files)
        self.assertEqual(dict(counts), V0_COUNTS)


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(buckets))
    return tests


if __name__ == "__main__":
    unittest.main()

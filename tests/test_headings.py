"""PARSE-5: heading detectors (pipeline/headings.py).

5a: Heading value and HeadingDetector interface.
5b: MarkdownHeadings (plus the corpus golden fingerprint).

Run: uv run python -m unittest discover tests
"""
import dataclasses
import doctest
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import headings  # noqa: E402
from pipeline.headings import Heading, HeadingDetector, MarkdownHeadings  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
GOLDEN = ROOT / "tests/golden/markdown_headings_fingerprint.json"


class HeadingValue(unittest.TestCase):
    def test_fields(self):
        h = Heading(line=2, level=2, text="Purpose")
        self.assertEqual((h.line, h.level, h.text), (2, 2, "Purpose"))

    def test_frozen(self):
        h = Heading(line=2, level=2, text="Purpose")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            h.text = "Scope"

    def test_compared_by_value(self):
        self.assertEqual(Heading(0, 1, "Title"), Heading(0, 1, "Title"))
        self.assertNotEqual(Heading(0, 1, "Title"), Heading(0, 2, "Title"))


class HeadingDetectorProtocol(unittest.TestCase):
    def test_any_class_with_find_headings_satisfies_it(self):
        class Fake:
            def find_headings(self, lines: list[str]) -> list[Heading]:
                return [Heading(0, 1, lines[0])] if lines else []
        detector: HeadingDetector = Fake()
        self.assertEqual(detector.find_headings(["Title"]), [Heading(0, 1, "Title")])
        self.assertIsInstance(detector, HeadingDetector)


class MarkdownHeadingsDetector(unittest.TestCase):
    def find(self, lines):
        return MarkdownHeadings().find_headings(lines)

    def test_hash_heading_plus_title(self):
        self.assertEqual(self.find(["Title", "", "## Scope", "text"]),
                         [Heading(0, 1, "Title"), Heading(2, 2, "Scope")])

    def test_setext_heading_underline_not_reported(self):
        self.assertEqual(self.find(["Title", "", "Scope", "-----", "text"]),
                         [Heading(0, 1, "Title"), Heading(2, 2, "Scope")])

    def test_markdown_title_is_not_duplicated(self):
        self.assertEqual(self.find(["# Title", "", "text"]), [Heading(0, 1, "Title")])

    def test_hash_inside_fence_is_ignored(self):
        self.assertEqual(self.find(["Title", "", "```", "# not a heading", "```"]), [Heading(0, 1, "Title")])

    def test_nested_heading_is_ignored(self):
        self.assertEqual(self.find(["Title", "", "> # quoted"]), [Heading(0, 1, "Title")])

    def test_empty_inputs(self):
        self.assertEqual(self.find([]), [])
        self.assertEqual(self.find([""]), [])

    def test_sorted_by_line(self):
        found = self.find(["Title", "", "## B", "", "Scope", "-----", "", "### C"])
        self.assertEqual([h.line for h in found], sorted(h.line for h in found))

    def test_satisfies_the_protocol(self):
        self.assertIsInstance(MarkdownHeadings(), HeadingDetector)

    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_real_corpus_matches_golden_fingerprint(self):
        golden = json.loads(GOLDEN.read_text())
        counts = [(p.name, len(self.find(p.read_text(encoding="utf-8").split("\n"))))
                  for p in sorted(CLEAN_DIR.glob("*.txt"))]
        lines = "\n".join(f"{name} {n}" for name, n in counts)
        self.assertEqual(len(counts), golden["files"])
        self.assertEqual(sum(n for _, n in counts), golden["total_headings"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), golden["fingerprint_sha256"])


class ModuleShape(unittest.TestCase):
    def test_module_is_pure(self):
        source = (ROOT / "pipeline/headings.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"headings.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(headings))
    return tests


if __name__ == "__main__":
    unittest.main()

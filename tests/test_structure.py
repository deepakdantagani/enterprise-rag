"""PARSE-8a: structure(text), what markdown-it sees in one clean file (pipeline/structure.py).

Three facts from one parse: heading lines with their level, the underline lines of
underlined headings, and the line ranges of code fences and tables.

Run: uv run python -m unittest discover tests
"""
import doctest
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import structure as structure_module  # noqa: E402
from pipeline.structure import Structure, structure  # noqa: E402
from tests.truth import load_truth  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
GOLDEN = ROOT / "tests/golden/structure_fingerprint.json"


class Headings(unittest.TestCase):
    def test_hash_headings_with_level(self):
        self.assertEqual(structure("# T\n\n## A\ntext").headings, {0: 1, 2: 2})

    def test_dash_underline_is_level_two(self):
        found = structure("Summary\n-------\ntext")
        self.assertEqual(found.headings, {0: 2})
        self.assertEqual(found.underlines, {1})

    def test_equals_underline_is_level_one(self):
        found = structure("Title\n=====\n")
        self.assertEqual(found.headings, {0: 1})
        self.assertEqual(found.underlines, {1})

    def test_hash_heading_has_no_underline(self):
        self.assertEqual(structure("## A\ntext").underlines, set())

    def test_hash_inside_fence_is_not_a_heading(self):
        self.assertEqual(structure("intro\n\n```\n# not a heading\n```\n").headings, {})

    def test_heading_nested_in_a_quote_is_not_a_heading(self):
        self.assertEqual(structure("intro\n\n> # quoted\n").headings, {})

    def test_underline_below_many_lines_is_not_a_heading(self):
        yaml_block = "intro\n\n---\nroute: a\nmodel: b\n---\nafter"
        found = structure(yaml_block)
        self.assertEqual(found.headings, {})
        self.assertEqual(found.underlines, set())


class Protected(unittest.TestCase):
    def test_plain_text_has_no_protected_ranges(self):
        self.assertEqual(structure("# T\n\n## A\ntext").protected, [])

    def test_fence_and_table_ranges(self):
        text = "\n".join([
            "Title", "", "intro",
            "```", "key:", "  value", "```",          # fence on lines 3-6
            "", "text",
            "| a | b |", "| --- | --- |", "| 1 | 2 |", "| 3 | 4 |",  # table on lines 9-12
            "", "after",
        ])
        self.assertEqual(structure(text).protected, [(3, 7), (9, 13)])

    def test_fence_nested_in_a_list_is_protected(self):
        text = "- step\n\n  ```\n  Note:\n  ```\n"
        self.assertEqual(structure(text).protected, [(2, 5)])


class Shape(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(structure(""), Structure(headings={}, underlines=set(), protected=[]))

    def test_module_is_pure(self):
        source = (ROOT / "pipeline/structure.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"structure.py must be pure; found {forbidden!r}")


class TruthSet(unittest.TestCase):
    """PARSE-17: real files whose headings a person decided. structure only sees `#` and
    underlined headings, so it is judged on what it reports, not on the labels it cannot see."""

    def test_reports_no_false_heading(self):
        for truth in load_truth():
            false = set(structure(truth.text).headings) - set(truth.headings) - set(truth.known_gaps)
            self.assertEqual(false, set(), truth.name)

    def test_levels_match_where_the_author_wrote_them(self):
        for truth in load_truth():
            for line, level in structure(truth.text).headings.items():
                if line in truth.headings:
                    self.assertEqual(level, truth.headings[line], f"{truth.name}:{line}")

    def test_no_true_heading_is_inside_a_protected_range(self):
        for truth in load_truth():
            for start, end in structure(truth.text).protected:
                self.assertEqual([h for h in truth.headings if start <= h < end], [], truth.name)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_matches_golden_fingerprint(self):
        golden = json.loads(GOLDEN.read_text())
        found = [(p.name, structure(p.read_text(encoding="utf-8"))) for p in sorted(CLEAN_DIR.glob("*.txt"))]
        lines = "\n".join(f"{name} {len(s.headings)} {len(s.underlines)} {len(s.protected)}" for name, s in found)
        self.assertEqual(len(found), golden["files"])
        self.assertEqual(sum(len(s.headings) for _, s in found), golden["total_headings"])
        self.assertEqual(sum(len(s.underlines) for _, s in found), golden["total_underlines"])
        self.assertEqual(sum(len(s.protected) for _, s in found), golden["total_protected"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), golden["fingerprint_sha256"])


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(structure_module))
    return tests


if __name__ == "__main__":
    unittest.main()

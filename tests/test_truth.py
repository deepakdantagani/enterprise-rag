"""PARSE-17: the heading truth set (tests/fixtures/headings/) and its loader (tests/truth.py).

The truth was decided by a person reading each page. These tests only check that the
set is well formed; PARSE-8a and 8b are the tests that compare code against it.

Run: uv run python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.markdown import MARKDOWN  # noqa: E402
from tests.truth import FIXTURE_DIR, Truth, disagreements, load_truth  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"


class LoadTruth(unittest.TestCase):
    def test_one_entry_per_fixture_file_in_name_order(self):
        names = [t.name for t in load_truth()]
        self.assertEqual(names, sorted(p.name for p in FIXTURE_DIR.glob("*.txt")))
        self.assertEqual(len(names), 10)

    def test_line_numbers_are_ints(self):
        first = load_truth()[0]
        self.assertIsInstance(first, Truth)
        self.assertEqual(first.headings, {0: 1, 2: 1, 7: 1, 12: 1, 19: 1, 27: 1})
        self.assertEqual(first.known_gaps, {})

    def test_every_entry_says_why_and_where_it_came_from(self):
        for t in load_truth():
            self.assertTrue(t.why.strip(), t.name)
            self.assertTrue(t.source.startswith("dsid_"), t.name)


class TruthIsWellFormed(unittest.TestCase):
    def test_every_line_number_points_at_a_non_blank_line(self):
        for t in load_truth():
            lines = t.text.split("\n")
            for line in [*t.headings, *t.known_gaps]:
                self.assertLess(line, len(lines), f"{t.name}:{line}")
                self.assertTrue(lines[line].strip(), f"{t.name}:{line} is blank")

    def test_levels_are_one_to_six(self):
        for t in load_truth():
            for line, level in t.headings.items():
                self.assertIn(level, range(1, 7), f"{t.name}:{line}")

    def test_no_true_heading_inside_a_fence_or_table(self):
        for t in load_truth():
            for token in MARKDOWN.parse(t.text):
                if token.type in ("fence", "table_open"):
                    inside = [h for h in t.headings if token.map[0] <= h < token.map[1]]
                    self.assertEqual(inside, [], f"{t.name}: heading inside {token.type} {token.map}")

    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_fixtures_are_byte_copies_of_the_clean_files(self):
        for t in load_truth():
            self.assertEqual((FIXTURE_DIR / t.name).read_bytes(), (CLEAN_DIR / t.source).read_bytes(), t.name)


class Disagreements(unittest.TestCase):
    truth = Truth(name="x.txt", source="dsid_x", why="w", text="",
                  headings={0: 1, 2: 2, 9: 2}, known_gaps={5: "false heading", 9: "missed"})

    def test_matching_the_truth_except_known_gaps_is_clean(self):
        self.assertEqual(disagreements({0, 2, 5}, self.truth), [])

    def test_a_false_heading_is_reported(self):
        self.assertEqual(disagreements({0, 2, 5, 7}, self.truth), ["x.txt:7 reported, not a heading"])

    def test_a_missed_heading_is_reported(self):
        self.assertEqual(disagreements({0, 5}, self.truth), ["x.txt:2 is a heading, not reported"])

    def test_a_known_gap_that_now_passes_must_be_removed(self):
        self.assertEqual(disagreements({0, 2, 5, 9}, self.truth), ["x.txt:9 now correct, remove this known gap"])
        self.assertEqual(disagreements({0, 2}, self.truth), ["x.txt:5 now correct, remove this known gap"])


if __name__ == "__main__":
    unittest.main()

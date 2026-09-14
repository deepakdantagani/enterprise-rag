"""PARSE-5: heading detectors (pipeline/headings.py).

5a: Heading value and HeadingDetector interface.

Run: uv run python -m unittest discover tests
"""
import dataclasses
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import headings  # noqa: E402
from pipeline.headings import Heading, HeadingDetector  # noqa: E402


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


class ModuleShape(unittest.TestCase):
    def test_module_holds_only_the_two_names(self):
        source = (ROOT / "pipeline/headings.py").read_text()
        self.assertEqual(source.count("\nclass "), 2)
        self.assertEqual(source.count("\ndef "), 0)
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"headings.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(headings))
    return tests


if __name__ == "__main__":
    unittest.main()

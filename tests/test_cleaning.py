"""PARSE-1: text cleaning rules as a pure module (pipeline/cleaning.py).

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import cleaning  # noqa: E402
from pipeline.cleaning import clean_text, fix_structure, is_escaped, normalize, unescape  # noqa: E402


class CleanTextContract(unittest.TestCase):
    """The public entry point: clean_text(raw) -> CleanResult(text, was_escaped)."""

    def test_escaped_body_comes_back_with_real_newlines(self):
        result = clean_text("Title\n\nSummary:\\n\\n- one\\n- two\\n- three\\n- four\\n")
        self.assertEqual(result.text, "Title\n\nSummary:\n\n- one\n- two\n- three\n- four\n")
        self.assertTrue(result.was_escaped)

    def test_normal_text_only_gets_whitespace_tidy(self):
        result = clean_text("Title   \n\n\n\nBody.\n\n\n")
        self.assertEqual(result.text, "Title\n\nBody.\n")
        self.assertFalse(result.was_escaped)

    def test_empty_input(self):
        result = clean_text("")
        self.assertEqual((result.text, result.was_escaped), ("", False))

    def test_module_touches_no_files(self):
        source = (ROOT / "pipeline/cleaning.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"cleaning.py must be pure; found {forbidden!r}")


class Rule1Unescape(unittest.TestCase):
    def test_is_escaped_by_count_ratio(self):
        self.assertTrue(is_escaped("T\\n\\n- a\\n- b\\n- c\\n"))
        self.assertFalse(is_escaped("\n".join(f"line {i}" for i in range(50)) + "\nprintf '%s\\n'\n"))
        self.assertFalse(is_escaped(""))

    def test_escaped_file_with_real_newlines_inside_fences(self):
        body = "\\n".join(f"line {i}" for i in range(20))
        self.assertTrue(is_escaped("Title\n\n" + body + "\\n```\nreal\nlines\n```\\nmore"))

    def test_all_escape_kinds(self):
        self.assertEqual(unescape('a\\nb\\tc \\"q\\" caf\\u00e9 x\\\\y'), 'a\nb\tc "q" café x\\y')
        self.assertEqual(unescape(""), "")
        self.assertEqual(unescape("no escapes"), "no escapes")


class Rule2FixStructure(unittest.TestCase):
    def test_wiki_heading_and_table(self):
        self.assertEqual(fix_structure(["h1. A", "h3. B"]), ["# A", "### B"])
        self.assertEqual(fix_structure(["||a||b||", "| 1 | 2 |"]), ["| a | b |", "|---|---|", "| 1 | 2 |"])

    def test_numbered_setext_heading(self):
        self.assertEqual(fix_structure(["1) Access", "----------", "Body"]), ["## 1) Access", "Body"])
        self.assertEqual(fix_structure(["1. Intro", "========", "Body"]), ["# 1. Intro", "Body"])
        self.assertEqual(fix_structure(["Title", "-----"]), ["Title", "-----"])  # plain setext: leave to Markdown

    def test_missing_table_separator(self):
        self.assertEqual(fix_structure(["| A | B |", "| 1 | 2 |"]), ["| A | B |", "|---|---|", "| 1 | 2 |"])
        self.assertEqual(fix_structure(["| A | B |", "|---|---|", "| 1 | 2 |"]), ["| A | B |", "|---|---|", "| 1 | 2 |"])
        self.assertEqual(fix_structure(["| lone row |"]), ["| lone row |"])

    def test_nested_lists_and_empty_pass_through(self):
        nested = ["- parent", "  - child", "    1) grandchild", "- next"]
        self.assertEqual(fix_structure(nested), nested)
        self.assertEqual(fix_structure([]), [])


class Rule3Normalize(unittest.TestCase):
    def test_whitespace(self):
        self.assertEqual(normalize("a  \n\n\n\nb\n\n\n"), "a\n\nb\n")
        self.assertEqual(normalize("Title"), "Title\n")
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("   \n\n"), "")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(cleaning))
    return tests


if __name__ == "__main__":
    unittest.main()

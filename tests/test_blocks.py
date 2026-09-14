"""PARSE-7: top-level blocks from markdown-it (pipeline/blocks.py).

7a: Block value and the token-to-kind table.

Run: uv run python -m unittest discover tests
"""
import dataclasses
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import blocks as blocks_module  # noqa: E402
from pipeline.blocks import KIND_OF_TOKEN, Block  # noqa: E402

TOKEN_KINDS = {
    "paragraph_open": "text",
    "bullet_list_open": "list",
    "ordered_list_open": "list",
    "heading_open": "heading",
    "hr": "rule",
    "table_open": "table",
    "fence": "code",
    "code_block": "code",
    "blockquote_open": "quote",
    "html_block": "html",
}


class BlockValue(unittest.TestCase):
    def test_fields(self):
        b = Block(kind="list", start=7, end=11)
        self.assertEqual((b.kind, b.start, b.end), ("list", 7, 11))

    def test_lines_is_end_minus_start(self):
        self.assertEqual(Block("list", 7, 11).lines, 4)

    def test_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Block("list", 7, 11).kind = "text"

    def test_compared_by_value(self):
        self.assertEqual(Block("list", 7, 11), Block("list", 7, 11))
        self.assertNotEqual(Block("list", 7, 11), Block("text", 7, 11))


class KindOfToken(unittest.TestCase):
    def test_every_corpus_token_type_maps_to_its_kind(self):
        self.assertEqual(KIND_OF_TOKEN, TOKEN_KINDS)

    def test_exactly_eight_kinds(self):
        self.assertEqual(set(KIND_OF_TOKEN.values()),
                         {"text", "list", "heading", "rule", "table", "code", "quote", "html"})


class ModuleShape(unittest.TestCase):
    def test_module_holds_only_block_and_the_table(self):
        source = (ROOT / "pipeline/blocks.py").read_text()
        self.assertEqual(source.count("\nclass "), 1)
        self.assertEqual(source.count("\ndef "), 0)
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"blocks.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(blocks_module))
    return tests


if __name__ == "__main__":
    unittest.main()

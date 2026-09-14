"""PARSE-7: top-level blocks from markdown-it (pipeline/blocks.py).

7a: Block value and the token-to-kind table.
7b: blocks(text) (plus coverage and the corpus golden fingerprint).

Run: uv run python -m unittest discover tests
"""
import dataclasses
import doctest
import hashlib
import json
import sys
from collections import Counter
from unittest import mock
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import blocks as blocks_module  # noqa: E402
from pipeline.blocks import KIND_OF_TOKEN, Block, blocks  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
FIXTURES = ROOT / "tests/fixtures"
GOLDEN = ROOT / "tests/golden/blocks_fingerprint.json"

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


def every_nonblank_line_covered_once(text: str, found: list[Block]) -> bool:
    covered = Counter()
    for b in found:
        for i in range(b.start, b.end):
            covered[i] += 1
    return all(covered[i] == 1 for i, line in enumerate(text.split("\n")) if line.strip())


class Blocks(unittest.TestCase):
    def test_fenced_code_block(self):
        text = "\n".join(["Title"] + [""] * 9 + ["```", "a = 1", "b = 2", "c = 3", "```", "", "After."])
        self.assertIn(Block("code", 10, 15), blocks(text))

    def test_bullet_list_includes_trailing_blank_then_paragraph(self):
        text = "\n".join(["Title", "", "Intro:", "- a", "- b", "- c", "- d", "", "After."])
        found = blocks(text)
        self.assertIn(Block("list", 3, 8), found)
        self.assertIn(Block("text", 8, 9), found)

    def test_pipe_table_is_one_block(self):
        text = "\n".join(["Title", "", "| a | b |", "|---|---|", "| 1 | 2 |", "| 3 | 4 |"])
        self.assertIn(Block("table", 2, 6), blocks(text))

    def test_two_paragraphs(self):
        self.assertEqual(blocks("One.\n\nTwo."), [Block("text", 0, 1), Block("text", 2, 3)])

    def test_heading_block(self):
        self.assertIn(Block("heading", 2, 3), blocks("Title\n\n## Scope\ntext"))

    def test_nested_content_gets_no_separate_block(self):
        self.assertEqual(blocks("```\n# not a heading\n```"), [Block("code", 0, 3)])
        self.assertEqual(blocks("> - quoted item\n> - another"), [Block("quote", 0, 2)])

    def test_unknown_token_type_fails_loudly(self):
        with mock.patch.dict(KIND_OF_TOKEN, {}, clear=True):
            with self.assertRaises(KeyError) as ctx:
                blocks("Just a paragraph.")
        self.assertIn("paragraph_open", str(ctx.exception))

    def test_empty(self):
        self.assertEqual(blocks(""), [])

    def test_fixtures_are_fully_covered(self):
        for path in sorted(FIXTURES.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(every_nonblank_line_covered_once(text, blocks(text)), path.name)

    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_real_corpus_covered_and_matches_golden(self):
        golden = json.loads(GOLDEN.read_text())
        counts = []
        for path in sorted(CLEAN_DIR.glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            found = blocks(text)                        # parse once, use for both checks
            self.assertTrue(every_nonblank_line_covered_once(text, found), path.name)
            counts.append((path.name, len(found)))
        lines = "\n".join(f"{name} {n}" for name, n in counts)
        self.assertEqual(sum(n for _, n in counts), golden["total_blocks"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), golden["fingerprint_sha256"])


class ModuleShape(unittest.TestCase):
    def test_module_is_pure(self):
        source = (ROOT / "pipeline/blocks.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"blocks.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(blocks_module))
    return tests


if __name__ == "__main__":
    unittest.main()

"""PARSE-8b2: to_markdown(text), the clean text with `#`s on every heading line.

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
from pipeline import to_markdown as to_markdown_module  # noqa: E402
from pipeline.structure import structure  # noqa: E402
from pipeline.to_markdown import heading_lines, label_lines, to_markdown  # noqa: E402
from tests.truth import disagreements, load_truth  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
GOLDEN = ROOT / "tests/golden/markdown_fingerprint.json"
BODY = "This is body text."


def intended_headings(text: str) -> set[int]:
    found = structure(text)
    title = {0} if text.split("\n")[0].strip() else set()
    return title | set(found.headings) | label_lines(text.split("\n"), found)


class WritesTheHashes(unittest.TestCase):
    def test_line_zero_is_the_title(self):
        self.assertEqual(to_markdown(f"Overview:\n\n{BODY}"), f"# Overview:\n\n{BODY}")

    def test_a_label_becomes_level_two(self):
        self.assertEqual(to_markdown(f"Title\n\nOverview:\n\n{BODY}"), f"# Title\n\n## Overview:\n\n{BODY}")

    def test_an_underlined_heading_is_rewritten_and_its_underline_emptied(self):
        self.assertEqual(to_markdown(f"Summary\n---\n{BODY}"), f"## Summary\n\n{BODY}")
        self.assertEqual(to_markdown(f"Title\n=====\n{BODY}"), f"# Title\n\n{BODY}")

    def test_hash_headings_are_left_alone(self):
        text = f"# Title\n\n## A\n{BODY}\n\n###   Spaced   \n{BODY}"
        self.assertEqual(to_markdown(text), text)

    def test_a_label_inside_a_fence_is_left_alone(self):
        text = f"# Title\n\n{BODY}\n\n```\n\nNote:\nx\n```\n"
        self.assertEqual(to_markdown(text), text)

    def test_indentation_is_dropped_from_a_rewritten_heading(self):
        self.assertEqual(to_markdown(f"Title\n\n  Summary\n  ---\n{BODY}"), f"# Title\n\n## Summary\n\n{BODY}")


class NoTitle(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(to_markdown(""), "")

    def test_blank_line_zero(self):
        self.assertEqual(to_markdown(f"\n{BODY}"), f"\n{BODY}")


class Properties(unittest.TestCase):
    samples = [t.text for t in load_truth()] + ["", "Title", f"Summary\n---\n{BODY}", "a\r\nb"]

    def test_same_number_of_lines(self):
        for text in self.samples:
            self.assertEqual(len(to_markdown(text).split("\n")), len(text.split("\n")))

    def test_every_heading_we_meant_is_a_hash_line(self):
        for text in self.samples:
            self.assertLessEqual(intended_headings(text), heading_lines(to_markdown(text)))

    def test_only_heading_lines_and_underlines_change(self):
        for text in self.samples:
            before, after = text.split("\n"), to_markdown(text).split("\n")
            changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
            allowed = intended_headings(text) | structure(text).underlines
            self.assertLessEqual(changed, allowed)


class TruthSet(unittest.TestCase):
    def test_the_hash_lines_of_the_output_are_the_true_headings(self):
        for truth in load_truth():
            self.assertEqual(disagreements(heading_lines(to_markdown(truth.text)), truth), [], truth.name)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_every_heading_we_meant_is_valid_markdown_and_the_corpus_matches_golden(self):
        golden = json.loads(GOLDEN.read_text())
        digest, headings, extra, files = hashlib.sha256(), 0, 0, 0
        for path in sorted(CLEAN_DIR.glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            markdown = to_markdown(text)
            meant, seen = intended_headings(text), set(structure(markdown).headings)
            self.assertLessEqual(meant, seen, f"{path.name}: markdown-it does not see {sorted(meant - seen)}")
            digest.update(f"{path.name} {hashlib.sha256(markdown.encode('utf-8')).hexdigest()}\n".encode())
            headings += len(meant)
            extra += len(seen - meant)
            files += 1
        self.assertEqual(files, golden["files"])
        self.assertEqual(headings, golden["total_headings"])
        self.assertEqual(extra, golden["extra_headings_markdown_it_sees"])
        self.assertEqual(digest.hexdigest(), golden["fingerprint_sha256"])


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(to_markdown_module))
    return tests


if __name__ == "__main__":
    unittest.main()

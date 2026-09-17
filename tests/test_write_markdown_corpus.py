"""PARSE-8c: write_markdown_corpus(clean_dir, markdown_dir) saves to_markdown of every clean
file and a manifest of its own; markdown_row is the pure row builder.

Run: uv run python -m unittest discover tests
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.corpus import write_markdown_corpus  # noqa: E402
from pipeline.manifest import markdown_row, sha256  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
GOLDEN = ROOT / "tests/golden/markdown_fingerprint.json"

CLEAN = "Deploy guide\n\nRollback\n--------\nSteps here.\n"
MARKDOWN = "# Deploy guide\n\n## Rollback\n\nSteps here.\n"


class MarkdownRow(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(markdown_row("page.txt", CLEAN, MARKDOWN, headings=2), {
            "file": "page.md",
            "clean_file": "page.txt",
            "clean_sha256": sha256(CLEAN),
            "md_sha256": sha256(MARKDOWN),
            "rewritten_lines": 3,
            "headings": 2,
        })

    def test_nothing_rewritten(self):
        self.assertEqual(markdown_row("page.txt", "# T\n", "# T\n", headings=1)["rewritten_lines"], 0)

    def test_a_different_line_count_is_refused(self):
        with self.assertRaises(ValueError):
            markdown_row("page.txt", "a\nb\n", "a\n", headings=0)


class WriteMarkdownCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.clean = self.tmp / "clean"
        self.markdown = self.tmp / "markdown"
        self.clean.mkdir()

    def test_one_markdown_file_and_one_row_per_clean_file(self):
        (self.clean / "one.txt").write_text(CLEAN)
        (self.clean / "two.txt").write_text("Only a title\n")
        rows = write_markdown_corpus(self.clean, self.markdown)
        self.assertEqual((self.markdown / "one.md").read_text(), MARKDOWN)
        self.assertEqual((self.markdown / "two.md").read_text(), "# Only a title\n")
        self.assertEqual([r["file"] for r in rows], ["one.md", "two.md"])
        self.assertEqual([r["rewritten_lines"] for r in rows], [3, 1])
        self.assertEqual([r["headings"] for r in rows], [2, 1])
        self.assertEqual(json.loads((self.markdown / "_manifest.json").read_text()), rows)

    def test_a_hash_page_has_many_headings_and_one_rewritten_line(self):
        (self.clean / "one.txt").write_text("Title\n\n## A\nBody.\n\n## B\nBody.\n")
        row = write_markdown_corpus(self.clean, self.markdown)[0]
        self.assertEqual((row["rewritten_lines"], row["headings"]), (1, 3))

    def test_the_clean_folder_is_not_touched(self):
        (self.clean / "one.txt").write_text(CLEAN)
        (self.clean / "_manifest.json").write_text("[]")
        before = {p.name: p.read_bytes() for p in self.clean.iterdir()}
        write_markdown_corpus(self.clean, self.markdown)
        self.assertEqual({p.name: p.read_bytes() for p in self.clean.iterdir()}, before)

    def test_the_clean_manifest_is_not_converted(self):
        (self.clean / "_manifest.json").write_text("[]")
        self.assertEqual(write_markdown_corpus(self.clean, self.markdown), [])

    def test_two_runs_give_the_same_rows(self):
        (self.clean / "one.txt").write_text(CLEAN)
        self.assertEqual(write_markdown_corpus(self.clean, self.markdown),
                         write_markdown_corpus(self.clean, self.markdown))

    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_real_corpus_matches_the_to_markdown_golden(self):
        golden = json.loads(GOLDEN.read_text())
        rows = write_markdown_corpus(CLEAN_DIR, self.markdown)
        lines = "".join(f"{r['clean_file']} {r['md_sha256']}\n" for r in rows)
        self.assertEqual(len(rows), golden["files"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), golden["fingerprint_sha256"])


if __name__ == "__main__":
    unittest.main()

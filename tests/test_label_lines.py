"""PARSE-8b1: label_lines(lines, found), the label-rule lines that are sections of this page.

Run: uv run python -m unittest discover tests
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.structure import structure  # noqa: E402
from pipeline.to_markdown import label_lines  # noqa: E402
from tests.truth import disagreements, load_truth  # noqa: E402

CLEAN_DIR = ROOT / "data/confluence/clean"
GOLDEN = ROOT / "tests/golden/label_lines_fingerprint.json"


def found_in(text: str) -> set[int]:
    return label_lines(text.split("\n"), structure(text))


class WhichLabelsCount(unittest.TestCase):
    def test_a_label_with_content_under_it(self):
        self.assertEqual(found_in("Title\n\nOverview:\ntext"), {2})

    def test_line_zero_is_the_title_not_a_label(self):
        self.assertNotIn(0, found_in("Overview:\n\nScope:\ntext"))

    def test_not_inside_a_fence(self):
        self.assertEqual(found_in("Title\n\nOverview:\ntext\n\n```\n\nNote:\nx\n```\n"), {2})

    def test_not_inside_a_table(self):
        text = "Title\n\nOverview:\ntext\n\n| a | b |\n| --- | --- |\n| Scope: | 2 |\n"
        self.assertEqual(found_in(text), {2})

    def test_a_markdown_heading_is_not_returned_again(self):
        text = "Title\n\n## Scope:\ntext\n\nOverview:\ntext\n\nOwners:\ntext"
        self.assertEqual(found_in(text), {5, 8})


class SameContextNoCut(unittest.TestCase):
    def test_question_lines_are_never_headings(self):
        for question in ("Q: Why?", "Q1: Why?", "Q) Why?"):
            text = f"Title\n\nFAQs:\ntext\n\n{question}\nA: Because."
            self.assertEqual(found_in(text), {2}, question)

    def test_a_label_directly_under_a_label_is_a_lead_in(self):
        self.assertEqual(found_in("Title\n\nCompression tiers\nTier definitions:\n1) Tier-A"), {2})

    def test_a_label_directly_under_a_markdown_heading_is_a_lead_in(self):
        text = "Title\n\nScope\n-----\ntext\n\nGoals:\ntext\n\nOwners:\ntext\n\n## Tiers\nTier definitions:\n1) Tier-A"
        self.assertEqual(found_in(text), {6, 9})

    def test_with_a_blank_line_between_both_are_sections(self):
        self.assertEqual(found_in("Title\n\nOverview\n\nPurpose\ntext"), {2, 4})


class MajorityStyle(unittest.TestCase):
    def test_markdown_majority_means_no_labels(self):
        text = "Title\n\n## A\ntext\n\n## B\ntext\n\n## C\ntext\n\nKey goals:\n- x"
        self.assertEqual(found_in(text), set())

    def test_label_majority_survives_a_stray_markdown_heading(self):
        labels = "".join(f"\nLabel {n}:\ntext\n" for n in range(20))
        text = "Title\n" + labels + "\n## - 2026-01-12: stray\n"
        self.assertEqual(len(found_in(text)), 20)

    def test_a_tie_goes_to_markdown(self):
        self.assertEqual(found_in("Title\n\n## A\nThis is body text.\n\nOverview:\nThis is body text."), set())


class TruthSet(unittest.TestCase):
    def test_disagrees_with_the_truth_only_on_known_gaps(self):
        for truth in load_truth():
            found = structure(truth.text)
            reported = {0} | set(found.headings) | label_lines(truth.text.split("\n"), found)
            self.assertEqual(disagreements(reported, truth), [], truth.name)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(CLEAN_DIR.is_dir(), "clean corpus not present (data/ is gitignored)")
    def test_matches_golden_fingerprint(self):
        golden = json.loads(GOLDEN.read_text())
        counts = [(p.name, len(found_in(p.read_text(encoding="utf-8")))) for p in sorted(CLEAN_DIR.glob("*.txt"))]
        lines = "\n".join(f"{name} {n}" for name, n in counts)
        self.assertEqual(len(counts), golden["files"])
        self.assertEqual(sum(n for _, n in counts), golden["total_label_lines"])
        self.assertEqual(sum(1 for _, n in counts if n), golden["files_with_label_lines"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), golden["fingerprint_sha256"])


if __name__ == "__main__":
    unittest.main()

"""PARSE-4: the plain-label heading rule (pipeline/label_rule.py).

4a: looks_like_a_sentence, is_key_with_long_value.
4b: is_label_shaped.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import label_rule  # noqa: E402
from pipeline.label_rule import (  # noqa: E402
    is_key_with_long_value,
    is_label_shaped,
    looks_like_a_sentence,
)


class LooksLikeASentence(unittest.TestCase):
    def test_sentence_starter_word(self):
        self.assertTrue(looks_like_a_sentence("The service restarts on failure"))

    def test_comma_and_more_than_eight_words(self):
        self.assertTrue(looks_like_a_sentence(
            "Manual triage is slow, remediation must be conservative, safe, and audited"))

    def test_comma_but_short_is_still_a_label(self):
        self.assertFalse(looks_like_a_sentence("Testing, canaries and chaos simulation:"))

    def test_real_lines(self):
        self.assertTrue(looks_like_a_sentence(
            "This playbook defines the Scheduler Health Oracle (SHO) — an auditable"))
        self.assertFalse(looks_like_a_sentence("Why SHO: problem statement"))
        self.assertFalse(looks_like_a_sentence("Overview:"))


class IsKeyWithLongValue(unittest.TestCase):
    def test_field_with_long_value(self):
        self.assertTrue(is_key_with_long_value(
            "Owner: Identity and Access team second approver required"))

    def test_allowed_shapes_are_not_fields(self):
        for line in ("Goals:",
                     "Appendix: Example Mappings",
                     "Stage 4: Expand to Dedicated deployments today",
                     "Q: Can we extend a lease mid-window?",
                     "Why SHO: problem statement"):
            self.assertFalse(is_key_with_long_value(line), line)

    def test_no_colon_is_not_a_field(self):
        self.assertFalse(is_key_with_long_value("High-level design"))


class IsLabelShaped(unittest.TestCase):
    def test_accepted_labels(self):
        for line in ("Rollout & Risk Controls",
                     "Phase 1: Data-source plumbing (Week 1-3)",
                     "Testing, canaries and chaos simulation:"):
            self.assertTrue(is_label_shaped(line), line)

    def test_too_long(self):
        self.assertFalse(is_label_shaped("x" * 81))
        self.assertFalse(is_label_shaped(" ".join(["word"] * 13)))

    def test_block_markers(self):
        for start in ("| a | b |", "> quote", "```", "# Heading", "---", "***", "___", "{", "}", "[x]", "]"):
            self.assertFalse(is_label_shaped(start), start)

    def test_closing_punctuation(self):
        for line in ("Ends with a period.", "Ends with semicolon;", "Ends with comma,"):
            self.assertFalse(is_label_shaped(line), line)

    def test_sentence_or_field_from_4a(self):
        self.assertFalse(is_label_shaped("We should not treat this as a heading"))
        self.assertFalse(is_label_shaped("Owner: Identity and Access team, second approver required"))

    def test_no_real_word_or_flag_like(self):
        for line in ("--kvcache-async", "123", "/usr/local/bin", "- bullet"):
            self.assertFalse(is_label_shaped(line), line)

    def test_empty(self):
        self.assertFalse(is_label_shaped(""))

    def test_real_lines_shape_only(self):
        expected = [("Scheduler Health Oracle and Self‑Heal Procedures", True),
                    ("Overview:", True),
                    ("This playbook defines the Scheduler Health Oracle (SHO) — an auditable", False),
                    ("Audience:", True),
                    ("- Oncall SREs and runtime engineers", False),
                    ("Why SHO: problem statement", True),
                    ("High-level design", True)]
        for line, want in expected:
            self.assertEqual(is_label_shaped(line), want, line)


class PureModule(unittest.TestCase):
    def test_module_touches_no_files(self):
        source = (ROOT / "pipeline/label_rule.py").read_text()
        for forbidden in ("open(", "read_text", "write_text", "Path(", "import os", "import json"):
            self.assertNotIn(forbidden, source, f"label_rule.py must be pure; found {forbidden!r}")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(label_rule))
    return tests


if __name__ == "__main__":
    unittest.main()

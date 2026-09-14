"""PARSE-4: the plain-label heading rule (pipeline/label_rule.py).

4a: looks_like_a_sentence, is_key_with_long_value.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import label_rule  # noqa: E402
from pipeline.label_rule import is_key_with_long_value, looks_like_a_sentence  # noqa: E402


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

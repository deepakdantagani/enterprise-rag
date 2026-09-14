"""Tests for the active pipeline: pipeline.preprocess and pipeline.structure.

Run: python3 -m unittest discover tests   (no third-party deps needed for this file)
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import preprocess as pre  # noqa: E402
from pipeline import structure  # noqa: E402
from pipeline.structure import bucket, label_flags  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Preprocess(unittest.TestCase):
    def test_escaped_body_is_unescaped(self):
        raw = "Title\n\nSummary:\\n\\n- one\\n- two\\n\\nSay \\\"hi\\\" and a real \\\\ backslash\\n"
        self.assertTrue(pre.is_escaped(raw))
        clean = pre.normalize(pre.unescape(raw))
        self.assertIn("Summary:\n\n- one\n- two", clean)
        self.assertIn('Say "hi" and a real \\ backslash', clean)

    def test_tab_and_unicode_escapes(self):
        raw = "T\n\n" + "a\\tb\\n" * 5 + "caf\\u00e9\\n"
        self.assertTrue(pre.is_escaped(raw))
        self.assertIn("a\tb", pre.unescape(raw))
        self.assertIn("caf\u00e9", pre.unescape(raw))

    def test_escaped_file_with_real_newlines_in_fences(self):
        body = "\\n".join(f"line {i}" for i in range(20))
        raw = "Title\n\n" + body + "\\n```\nreal\nlines\n```\\nmore"
        self.assertTrue(pre.is_escaped(raw), "literal \\n outnumbers real newlines")

    def test_mixed_file_is_left_alone(self):
        raw = "\n".join(f"line {i}" for i in range(50)) + "\nprintf '%s\\n' done\n"
        self.assertFalse(pre.is_escaped(raw))

    def test_numbered_setext_heading_becomes_atx(self):
        out = pre.normalize("1) Access & Permissions\n----------------------\nBody\n")
        self.assertTrue(out.startswith("## 1) Access & Permissions\nBody"))

    def test_numbered_setext_with_equals_becomes_h1(self):
        out = pre.normalize("1. Intro\n========\nBody\n")
        self.assertTrue(out.startswith("# 1. Intro\nBody"))

    def test_wiki_heading_levels(self):
        self.assertEqual(pre.normalize("h1. A\nh3. B\n"), "# A\n### B\n")

    def test_missing_table_separator_is_inserted(self):
        out = pre.normalize("| A | B |\n| 1 | 2 |\n")
        self.assertEqual(out, "| A | B |\n|---|---|\n| 1 | 2 |\n")

    def test_existing_separator_untouched(self):
        src = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        self.assertEqual(pre.normalize(src), src)

    def test_wiki_markup_converted(self):
        out = pre.normalize("h2. Scope\n||a||b||\n| 1 | 2 |\n")
        self.assertEqual(out, "## Scope\n| a | b |\n|---|---|\n| 1 | 2 |\n")

    def test_whitespace_normalised(self):
        self.assertEqual(pre.normalize("a  \n\n\n\nb\n\n\n"), "a\n\nb\n")


class PreprocessEdgeCases(unittest.TestCase):
    def test_empty_input_stays_empty(self):
        self.assertFalse(pre.is_escaped(""))
        self.assertEqual(pre.unescape(""), "")
        self.assertEqual(pre.fix_structure([]), [])
        self.assertEqual(pre.normalize(""), "")
        self.assertEqual(pre.normalize("   \n\n"), "")
        self.assertEqual(pre.clean_one(""), ("", False))

    def test_single_line_without_newline(self):
        self.assertEqual(pre.normalize("Title"), "Title\n")

    def test_lone_pipe_line_is_not_a_table(self):
        self.assertEqual(pre.fix_structure(["| just one row |"]), ["| just one row |"])

    def test_nested_lists_pass_through_untouched(self):
        nested = ["- parent", "  - child", "    1) grandchild", "      a. great-grandchild", "- next parent"]
        self.assertEqual(pre.fix_structure(nested), nested)
        self.assertEqual(pre.normalize("\n".join(nested) + "\n"), "\n".join(nested) + "\n")

    def test_underline_without_list_marker_is_left_for_markdown(self):
        # "Title" + "-----" is a valid setext heading already; we do not rewrite it.
        self.assertEqual(pre.fix_structure(["Title", "-----"]), ["Title", "-----"])

    def test_run_on_a_folder(self):
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir, clean_dir = Path(tmp) / "raw", Path(tmp) / "clean"
            raw_dir.mkdir()
            (raw_dir / "dsid_1__a.txt").write_text("Title\n\nA:\\n- x\\n- y\\n- z\\n- w\\n")
            (raw_dir / "dsid_2__b.txt").write_text("Plain\n\nBody.\n")
            manifest, counts = pre.run(raw_dir, clean_dir)
            self.assertEqual(counts, {"escaped": 1, "unchanged": 1, "whitespace_only": 0, "structure_fixed": 0})
            self.assertEqual((clean_dir / "dsid_1__a.txt").read_text(), "Title\n\nA:\n- x\n- y\n- z\n- w\n")
            saved = json.loads((clean_dir / "_manifest.json").read_text())
            self.assertEqual([m["file"] for m in saved], ["dsid_1__a.txt", "dsid_2__b.txt"])
            self.assertTrue(saved[0]["was_escaped"]); self.assertFalse(saved[1]["was_escaped"])

    def test_run_on_empty_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            manifest, counts = pre.run(Path(tmp), Path(tmp) / "clean")
            self.assertEqual(manifest, [])
            self.assertEqual(sum(counts.values()), 0)


class Buckets(unittest.TestCase):
    def test_empty_text_is_prose(self):
        self.assertEqual(bucket(""), "D_prose")

    def test_hash_wins_over_setext_and_lists(self):
        self.assertEqual(bucket("Intro\n-----\n\n# Real\n\n- item"), "A_hash")

    def test_fenced_code_alone_is_bucket_c(self):
        self.assertEqual(bucket("Title\n\n```\nx = 1\n```"), "C_plain_labels")

    def test_bucket_detection(self):
        self.assertEqual(bucket("# T\n\ntext"), "A_hash")
        self.assertEqual(bucket("T\n---\n\ntext"), "B_setext")
        self.assertEqual(bucket("Label\n\n- item"), "C_plain_labels")
        self.assertEqual(bucket("Just prose.\n\nMore prose."), "D_prose")


class LabelRule(unittest.TestCase):
    def labels(self, text):
        lines = text.splitlines()
        flags = label_flags(lines)
        return [lines[i] for i in range(len(lines)) if flags[i]]

    def test_typical_sections(self):
        text = (FIXTURES / "typical.md").read_text()
        found = self.labels(text)
        for expected in ["Overview", "Goals", "Scope", "Key Definitions", "Escalation matrix", "Contacts", "Document History"]:
            self.assertIn(expected, found)
        self.assertEqual(found[0], text.splitlines()[0], "line 1 is the title")

    def test_title_always_promoted_even_if_long(self):
        long_title = "Console hint palette: contextual templates for dashboards, rollouts, and cost views (Design Spec, 2026)"
        self.assertEqual(self.labels(long_title + "\n\nBody."), [long_title])

    def test_rejects_sentences_lists_and_kv(self):
        text = "T\n\nThe quick brown fox jumps over the lazy dog, twice.\n\n- item\n\nOwner: Identity and Access team (eng-infra) is here\n\nEnds with period.\n"
        self.assertEqual(self.labels(text), ["T"])

    def test_skips_fenced_code(self):
        text = "T\n\n```py\n\ndef capture_and_send(prompt):\n\n```\n\nReal Label\n\nBody."
        self.assertEqual(self.labels(text), ["T", "Real Label"])

    def test_stacked_labels(self):
        self.assertEqual(self.labels("T\n\nParent\nChild label\n\nBody."), ["T", "Parent", "Child label"])

    def test_label_followed_by_list_or_table(self):
        self.assertEqual(self.labels("T\n\nGoals:\n- a\n\nMatrix:\n| a | b |"), ["T", "Goals:", "Matrix:"])

    def test_each_rejection_reason(self):
        """One line per reason a label-shaped line is rejected. All must be rejected."""
        rejected = [
            "x" * 81,                                            # too long
            "one two three four five six seven eight nine ten eleven twelve thirteen",  # too many words
            "| a | b |", "> quote", "```", "# already", "---", "{",  # block markers
            "Ends with a period.", "ends with semicolon;", "ends, with comma,",
            "The quick brown fox jumps over the lazy dog, twice, today",  # sentence-like: comma + 9 words
            "We should not treat this as a heading",              # sentence starter
            "Owner: Identity and Access team, second approver required for this",  # key: long value
            "64", "1.0", "--kvcache-async", "/tmp/replay.tgz",     # no letters / starts with - or /
            "- a list item", "1) numbered item", "a. lettered item",
            "  indented line",
        ]
        text = "T\n\n" + "\n\n".join(rejected) + "\n"
        self.assertEqual(self.labels(text), ["T"])

    def test_each_acceptance_shape(self):
        accepted = ["Overview", "Goals:", "Rollout & Risk Controls", "Appendix: Example Mappings",
                    "Phase 1: Data-source plumbing (Week 1–3)", "Step 2 — Tenant bootstrap procedure",
                    "Testing, canaries and chaos simulation:", "FAQ (short):", "What is a tenant?"]
        text = "T\n\n" + "\n\n".join(accepted) + "\n"
        self.assertEqual(self.labels(text), ["T"] + accepted)

    def test_numbered_heading_with_blank_lines_around_it(self):
        text = "T\n\n3) Escalation heuristics (decision ladder)\n\nBody.\n\n10.1 Weekly cadence\n\nMore."
        self.assertEqual(self.labels(text), ["T", "3) Escalation heuristics (decision ladder)", "10.1 Weekly cadence"])

    def test_numbered_list_items_are_not_headings(self):
        tight_list = "T\n\n1) first item\n2) second item\n3) third item\n\nBody."
        self.assertEqual(self.labels(tight_list), ["T"])
        with_sub_bullets = "T\n\n1) Ingestion and Latency\n - Metrics delivered within 60s.\n\n2) Coverage\n - Labels present."
        self.assertEqual(self.labels(with_sub_bullets), ["T"])

    def test_labelled_keys_are_headings_but_fields_are_not(self):
        text = ("T\n\nStage 4: Expand to Dedicated and Private deployments today\n\n"
                "Q: Can we extend a lease mid-window for a customer?\nA: Yes, with a new request and a fresh approval.\n\n"
                "Appendix B: Quick decision flow for the oncall engineer\n\n"
                "Owner: Identity and Access team second approver required\n\nBody.")
        self.assertEqual(self.labels(text), ["T", "Stage 4: Expand to Dedicated and Private deployments today",
                                             "Q: Can we extend a lease mid-window for a customer?",
                                             "Appendix B: Quick decision flow for the oncall engineer"])

    def test_label_needs_blank_line_or_label_above(self):
        self.assertEqual(self.labels("T\n\nBody text here.\nNot a label\n\nIs a label"), ["T", "Is a label"])

    def test_empty_and_fence_only_input(self):
        self.assertEqual(label_flags([]), [])
        self.assertEqual(label_flags(["```", "code", "```"]), [False, False, False])

    def test_unclosed_fence_swallows_the_rest(self):
        self.assertEqual(self.labels("T\n\n```\nnever closed\n\nWould be label"), ["T"])

    def test_labels_helper_returns_line_numbers(self):
        self.assertEqual(structure.labels("T\n\nOverview\n\nBody."), [(1, "T"), (3, "Overview")])


class Explain(unittest.TestCase):
    def test_explain_gives_a_reason_per_line(self):
        text = "Title\n\nOverview\n\nThe body sentence with commas, and many many words here\n- item\n"
        rows = structure.explain(text)
        self.assertEqual([r["line"] for r in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(rows[0]["decision"], "HEADING"); self.assertIn("title", rows[0]["reason"])
        self.assertEqual(rows[1]["decision"], "");         self.assertEqual(rows[1]["reason"], "blank")
        self.assertEqual(rows[2]["decision"], "HEADING")
        self.assertEqual(rows[4]["decision"], "");         self.assertIn("sentence", rows[4]["reason"])
        self.assertEqual(rows[5]["decision"], "");         self.assertIn("list", rows[5]["reason"])

    def test_explain_reports_no_blank_line_above(self):
        rows = structure.explain("Title\n\nBody text ends here.\nNot a label\n")
        self.assertIn("line above", rows[3]["reason"])

    def test_explain_empty(self):
        self.assertEqual(structure.explain(""), [])


class LabelRuleRecall(unittest.TestCase):
    def test_recall_on_fixture_with_hash_headings(self):
        text = (FIXTURES / "blockquote.md").read_text()
        report = structure.recall_against_hash_headings([text])
        self.assertGreater(report["recall"], 0.75)
        self.assertEqual(report["true_headings"], 34)

    def test_recall_report_on_no_headings(self):
        report = structure.recall_against_hash_headings(["no headings here"])
        self.assertEqual(report["true_headings"], 0)
        self.assertIsNone(report["recall"])


def load_tests(loader, tests, ignore):
    """Also run the input -> output examples written in the pipeline docstrings."""
    import doctest
    tests.addTests(doctest.DocTestSuite(pre))
    tests.addTests(doctest.DocTestSuite(structure))
    return tests


if __name__ == "__main__":
    unittest.main()

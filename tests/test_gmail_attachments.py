"""GMAIL-7a: attachment_names(text) lists the file names on labelled lines such as "Attachments: a.pdf, b.xlsx".

Run: uv run python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail.attachments import attachment_names  # noqa: E402
from pipeline.gmail.cleaning import clean_thread  # noqa: E402
from pipeline.gmail.headers import parse_headers  # noqa: E402
from pipeline.gmail.messages import split_messages  # noqa: E402
from pipeline.gmail.quotes import strip_quotes  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"


class LabelledLines(unittest.TestCase):
    def test_one_name_with_a_type_in_brackets(self):
        self.assertEqual(attachment_names("Attachment: Greenline_PO_3042.pdf (application/pdf)"), ["Greenline_PO_3042.pdf"])

    def test_two_names_in_order(self):
        text = "Attachments: entity_mapping_template.xlsx, Greenline_SOW_v2.docx"
        self.assertEqual(attachment_names(text), ["entity_mapping_template.xlsx", "Greenline_SOW_v2.docx"])

    def test_lowercase_and_uppercase_labels(self):
        for label in ["attachments", "ATTACHMENTS", "attachment", "Attachment(s)"]:
            with self.subTest(label=label):
                self.assertEqual(attachment_names(f"{label}: ClearWave_MSA_redline_v1.docx"), ["ClearWave_MSA_redline_v1.docx"])

    def test_attached_with_a_name_counts(self):
        self.assertEqual(attachment_names("Attached: cascade_vpc_ranges.csv"), ["cascade_vpc_ranges.csv"])

    def test_labels_that_mean_the_same_thing(self):
        for label in ["Attachments referenced", "Attachments included", "Attachment stubs", "Attachment stub", "Attachments stub", "Attachment(s) referenced"]:
            with self.subTest(label=label):
                self.assertEqual(attachment_names(f"{label}: plan.pdf"), ["plan.pdf"])

    def test_a_bullet_or_indent_before_the_label(self):
        self.assertEqual(attachment_names("- Attachments: a.pdf"), ["a.pdf"])
        self.assertEqual(attachment_names("   Attachment: b.pdf"), ["b.pdf"])

    def test_separators_semicolon_and_the_word_and(self):
        self.assertEqual(attachment_names("Attachments: a.pdf; b.xlsx and c.csv"), ["a.pdf", "b.xlsx", "c.csv"])

    def test_names_inside_square_brackets(self):
        text = "Attachments: [Redwood-trial-plan-v1.pdf (pdf, 320 KB)], [prompt-set-v2.json]"
        self.assertEqual(attachment_names(text), ["Redwood-trial-plan-v1.pdf", "prompt-set-v2.json"])

    def test_a_name_inside_round_brackets_after_a_name_with_no_extension(self):
        text = "Attachments: Mendr_MSA_v2.pdf; Mendr_Logo_ZIP (brand-guidelines.pdf)"
        self.assertEqual(attachment_names(text), ["Mendr_MSA_v2.pdf", "brand-guidelines.pdf"])

    def test_several_labelled_lines_in_one_text(self):
        text = "Hi.\nAttachment: a.pdf\nBody text.\nAttachments: b.xlsx, c.csv"
        self.assertEqual(attachment_names(text), ["a.pdf", "b.xlsx", "c.csv"])


class WhatIsNotAName(unittest.TestCase):
    def test_a_sentence_after_attached_gives_nothing(self):
        text = "Attached: sample invoice mock (internal) and entity mapping template. No need to do a formal review."
        self.assertEqual(attachment_names(text), [])

    def test_none_and_promises_give_nothing(self):
        for value in ["none", "(will attach)", "none (will accept your links)", "(original attachments retained)", "detailed-sizing-spreadsheet (to be uploaded)"]:
            with self.subTest(value=value):
                self.assertEqual(attachment_names(f"Attachments: {value}"), [])

    def test_a_size_or_a_version_is_not_a_name(self):
        text = "Attachment: Novus-VPC-Requirements.pdf (1.2MB), notes v1.2 and TLS1.3 (2 KB)"
        self.assertEqual(attachment_names(text), ["Novus-VPC-Requirements.pdf"])

    def test_a_mime_type_is_not_a_name(self):
        text = "Attachment: model.xlsx (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)"
        self.assertEqual(attachment_names(text), ["model.xlsx"])

    def test_a_type_written_in_capitals_is_not_a_name(self):
        text = "Attachments: network-flow-sample-20270520.tar.gz (TAR.GZ, 18MB), CAIQ_export.csv (CSV)"
        self.assertEqual(attachment_names(text), ["network-flow-sample-20270520.tar.gz", "CAIQ_export.csv"])

    def test_an_email_address_or_a_domain_is_not_a_name(self):
        text = "Attachments: ops@redwood.com, inference.redwood.net, report.pdf"
        self.assertEqual(attachment_names(text), ["report.pdf"])

    def test_abbreviations_are_not_names(self):
        self.assertEqual(attachment_names("Attachments: e.g. the plan, i.e. the old one, approx. 2 pages"), [])


class NamesInsideOtherText(unittest.TestCase):
    def test_a_sentence_before_the_name_is_dropped(self):
        text = "Attachments: suggested week-of-warmth language in week-of-warmth-offer-terms.pdf"
        self.assertEqual(attachment_names(text), ["week-of-warmth-offer-terms.pdf"])

    def test_trailing_punctuation_is_dropped(self):
        self.assertEqual(attachment_names("Attachments: see plan.pdf."), ["plan.pdf"])

    def test_unusual_extensions_are_found(self):
        text = "Attachments: MAP-template-v1.gdoc (link), MAP-slate-v1.gslides, contacts.vcf, tool.js"
        self.assertEqual(attachment_names(text), ["MAP-template-v1.gdoc", "MAP-slate-v1.gslides", "contacts.vcf", "tool.js"])

    def test_a_path_or_link_gives_its_last_segment(self):
        self.assertEqual(attachment_names("Attachments: Diva/Diva-crossconnect.pdf"), ["Diva-crossconnect.pdf"])
        self.assertEqual(attachment_names("Attachments: https://drive.redwood.com/shared/2027/tooling-bundle.xlsx"), ["tooling-bundle.xlsx"])

    def test_a_name_with_spaces_is_cut_to_its_last_word(self):
        self.assertEqual(attachment_names("Attachments: Q3 Report.pdf"), ["Report.pdf"])


class RepeatsAndOrder(unittest.TestCase):
    def test_a_repeated_name_is_listed_once_in_first_seen_order(self):
        text = "Attachments: b.pdf, a.pdf, b.pdf\nAttachment: a.pdf, c.pdf"
        self.assertEqual(attachment_names(text), ["b.pdf", "a.pdf", "c.pdf"])

    def test_names_that_differ_only_in_case_are_different(self):
        self.assertEqual(attachment_names("Attachments: Plan.pdf, plan.pdf"), ["Plan.pdf", "plan.pdf"])


class LinesThatAreNotRead(unittest.TestCase):
    def test_a_label_in_the_middle_of_a_sentence_is_not_read(self):
        self.assertEqual(attachment_names("See the Attachment: plan.pdf below"), [])
        self.assertEqual(attachment_names("Please review the attached and reply with: plan.pdf"), [])

    def test_a_quoted_line_is_not_read(self):
        self.assertEqual(attachment_names("> Attachment: ethan_zhou_resume.pdf (application/pdf, 213KB)"), [])

    def test_bracket_lines_and_bullet_lists_wait_for_7b(self):
        self.assertEqual(attachment_names("[Attachment: Helios_MSA_redline.docx (docx - redline)]"), [])
        self.assertEqual(attachment_names("Attachments:\n- SustainCo_Scorecard.xlsx (xlsx)\n- SustainCo_SelfID.pdf (pdf)"), [])

    def test_other_labels_are_not_read(self):
        self.assertEqual(attachment_names("Attaching: Procurement_requirements.xlsx"), [])
        self.assertEqual(attachment_names("Attachments in thread: plan.pdf"), [])

    def test_no_label_and_empty_text(self):
        self.assertEqual(attachment_names("Just some text with plan.pdf inside."), [])
        self.assertEqual(attachment_names(""), [])


class Rerunning(unittest.TestCase):
    TEXT = "Attachments: a.pdf, b.xlsx\nAttachment: a.pdf"

    def test_same_input_gives_same_output(self):
        self.assertEqual(attachment_names(self.TEXT), attachment_names(self.TEXT))

    def test_each_call_returns_a_new_list(self):
        first = attachment_names(self.TEXT)
        first.append("changed.pdf")
        self.assertEqual(attachment_names(self.TEXT), ["a.pdf", "b.xlsx"])


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        messages_with_names = names = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            for block in split_messages(text).blocks:
                found = attachment_names(strip_quotes(parse_headers(block).body).text)
                messages_with_names += bool(found)
                names += len(found)
                self.assertEqual(len(found), len(set(found)))
        # Both counted by a separately written script (plain string checks, not this module) and
        # compared message by message: it first missed three label spellings, then agreed on every message.
        self.assertEqual(messages_with_names, 231_421)
        self.assertEqual(names, 347_011)


if __name__ == "__main__":
    unittest.main()

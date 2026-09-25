"""GMAIL-4: parse_headers(block) reads From, To, Cc, Date (or Sent) and Subject out of one message block.

Run: uv run python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail.cleaning import clean_thread  # noqa: E402
from pipeline.gmail.headers import parse_headers  # noqa: E402
from pipeline.gmail.messages import split_messages  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"

VIVEK = (
    "From: Vivek Kulkarni <vivek.kulkarni@redwood.ai>\n"
    "To: Amal Khan <amal.khan@greenlinehealth.com>\n"
    "Cc: Kimberly Park <kimberly_park@redwood.ai>, Marissa Cole <marissa_cole@redwood.ai>\n"
    "Date: Thu, 25 Jun 2026 11:05:00 -07:00\n"
    "Subject: Re: Invoice & VAT approach for multi-entity pilot (Greenline)\n"
    "\n"
    "Thanks Amal.\n"
)


class TheFiveFields(unittest.TestCase):
    def test_real_block_from_the_story(self):
        parsed = parse_headers(VIVEK)
        self.assertEqual(parsed.from_, "Vivek Kulkarni <vivek.kulkarni@redwood.ai>")
        self.assertEqual(parsed.to, ["Amal Khan <amal.khan@greenlinehealth.com>"])
        self.assertEqual(
            parsed.cc,
            ["Kimberly Park <kimberly_park@redwood.ai>", "Marissa Cole <marissa_cole@redwood.ai>"],
        )
        self.assertEqual(parsed.date_raw, "Thu, 25 Jun 2026 11:05:00 -07:00")
        self.assertEqual(parsed.subject, "Re: Invoice & VAT approach for multi-entity pilot (Greenline)")
        self.assertEqual(parsed.body, "Thanks Amal.")

    def test_no_cc_line_gives_an_empty_list(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).cc, [])

    def test_headers_in_any_order_are_all_found(self):
        block = "From: A <a@x.com>\nDate: d\nSubject: s\nTo: B <b@y.com>\nCc: C <c@z.com>\n\nHi\n"
        parsed = parse_headers(block)
        self.assertEqual((parsed.date_raw, parsed.subject), ("d", "s"))
        self.assertEqual((parsed.to, parsed.cc), (["B <b@y.com>"], ["C <c@z.com>"]))
        self.assertEqual(parsed.body, "Hi")

    def test_value_is_trimmed(self):
        block = "From:   A <a@x.com>  \nTo: B <b@y.com>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).from_, "A <a@x.com>")


class Recipients(unittest.TestCase):
    def test_split_on_commas_outside_angle_brackets(self):
        block = "From: A <a@x.com>\nTo: A <a@x>, B <b@y>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).to, ["A <a@x>", "B <b@y>"])

    def test_bare_addresses_are_kept_as_written(self):
        block = "From: A <a@x.com>\nTo: raj@x.com, Ana <ana@x.com>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).to, ["raj@x.com", "Ana <ana@x.com>"])

    def test_wrapped_recipient_line_is_joined(self):
        block = (
            "From: A <a@x.com>\n"
            "To: Amara Johnson <amara.johnson@example.com>,\n"
            "    Karthik Iyer <karthik.iyer@redwood.com>\n"
            "Date: Wed, 5 Jul 2028 08:02:00 -0400\n"
            "Subject: Re: Quick intro call\n"
            "\n"
            "Hi\n"
        )
        parsed = parse_headers(block)
        self.assertEqual(
            parsed.to,
            ["Amara Johnson <amara.johnson@example.com>", "Karthik Iyer <karthik.iyer@redwood.com>"],
        )
        self.assertEqual(parsed.date_raw, "Wed, 5 Jul 2028 08:02:00 -0400")
        self.assertEqual(parsed.subject, "Re: Quick intro call")

    def test_name_with_a_comma_is_split_and_the_fragment_has_no_email(self):
        block = "From: A <a@x.com>\nTo: Ruiz, Elena <elena.ruiz@novagrid.com>, Bo <bo@y.com>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(
            parse_headers(block).to,
            ["Ruiz", "Elena <elena.ruiz@novagrid.com>", "Bo <bo@y.com>"],
        )

    def test_from_is_kept_whole_even_with_a_comma_name(self):
        block = "From: Ruiz, Elena <elena.ruiz@novagrid.com>\nTo: B <b@y.com>\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).from_, "Ruiz, Elena <elena.ruiz@novagrid.com>")

    def test_none_and_semicolon_lists_are_kept_as_raw_text(self):
        block = "From: A <a@x.com>\nTo: (none)\nCc: Vanessa Ortiz; Rafael Mendes\nDate: d\nSubject: s\n\nHi\n"
        parsed = parse_headers(block)
        self.assertEqual(parsed.to, ["(none)"])
        self.assertEqual(parsed.cc, ["Vanessa Ortiz; Rafael Mendes"])

    def test_trailing_comma_leaves_no_empty_entry(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>,\nDate: d\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).to, ["B <b@y.com>"])


class DateAndSent(unittest.TestCase):
    def test_sent_is_used_when_there_is_no_date(self):
        block = "From: A <a@x.com>\nSent: Thu, Apr 24, 2025 9:12 AM\nTo: B <b@y.com>\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).date_raw, "Thu, Apr 24, 2025 9:12 AM")

    def test_date_wins_when_both_are_present(self):
        block = "From: A <a@x.com>\nDate: real\nSent: other\nTo: B <b@y.com>\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).date_raw, "real")

    def test_the_date_is_never_parsed_here(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>\nDate: not a date at all\nSubject: s\n\nHi\n"
        self.assertEqual(parse_headers(block).date_raw, "not a date at all")


class IgnoredAndUnknownLines(unittest.TestCase):
    def test_ignored_keys_leave_the_body_and_are_not_returned(self):
        block = (
            "From: A <a@x.com>\nTo: B <b@y.com>\nBcc: hidden@x.com\nReply-To: r@x.com\n"
            "References: <id-1@x>\nDate: d\nSubject: s\n\nHi\n"
        )
        parsed = parse_headers(block)
        self.assertEqual(parsed.body, "Hi")
        self.assertNotIn("hidden@x.com", repr(parsed))

    def test_attachments_line_after_the_headers_stays_in_the_body(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>\nDate: d\nSubject: s\nAttachments: plan.pdf\n\nHi\n"
        parsed = parse_headers(block)
        self.assertEqual(parsed.subject, "s")
        self.assertEqual(parsed.body, "Attachments: plan.pdf\n\nHi")

    def test_body_may_start_with_no_blank_line(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>\nDate: d\nSubject: s\nMaya,\nSee below.\n"
        self.assertEqual(parse_headers(block).body, "Maya,\nSee below.")

    def test_a_body_line_that_looks_like_a_header_is_not_read_after_a_blank_line(self):
        block = "From: A <a@x.com>\nTo: B <b@y.com>\nDate: d\nSubject: s\n\nTo: everyone\nHi\n"
        parsed = parse_headers(block)
        self.assertEqual(parsed.to, ["B <b@y.com>"])
        self.assertEqual(parsed.body, "To: everyone\nHi")


class BlocksWithoutHeaders(unittest.TestCase):
    def test_no_headers_gives_empty_fields_and_the_whole_block_as_body(self):
        block = "Just some prose.\nSecond line.\n"
        parsed = parse_headers(block)
        self.assertEqual((parsed.from_, parsed.date_raw, parsed.subject), ("", "", ""))
        self.assertEqual((parsed.to, parsed.cc), ([], []))
        self.assertEqual(parsed.body, "Just some prose.\nSecond line.")

    def test_a_first_line_with_an_unknown_key_is_not_a_header(self):
        parsed = parse_headers("urgent: call me\nMore.\n")
        self.assertEqual(parsed.from_, "")
        self.assertEqual(parsed.body, "urgent: call me\nMore.")

    def test_empty_block(self):
        parsed = parse_headers("")
        self.assertEqual((parsed.from_, parsed.to, parsed.cc, parsed.date_raw, parsed.subject, parsed.body),
                         ("", [], [], "", "", ""))

    def test_missing_field_is_empty_not_an_error(self):
        parsed = parse_headers("From: A <a@x.com>\nTo: B <b@y.com>\nDate: d\n\nHi\n")
        self.assertEqual(parsed.subject, "")


class Determinism(unittest.TestCase):
    def test_same_input_gives_same_output(self):
        self.assertEqual(parse_headers(VIVEK), parse_headers(VIVEK))


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        blocks = all_empty = no_from = no_to = no_subject = with_date = 0
        attachments_lines_in_blocks = attachments_lines_in_bodies = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            for block in split_messages(text).blocks:
                parsed = parse_headers(block)
                blocks += 1
                no_from += not parsed.from_
                no_to += not parsed.to
                no_subject += not parsed.subject
                with_date += bool(parsed.date_raw)
                all_empty += not (parsed.from_ or parsed.to or parsed.cc or parsed.date_raw or parsed.subject)
                attachments_lines_in_blocks += count_attachments_lines(block)
                attachments_lines_in_bodies += count_attachments_lines(parsed.body)
        self.assertEqual(blocks, 578_443)
        self.assertEqual(all_empty, 189)
        self.assertEqual(no_from, 189)
        self.assertEqual(no_to, 1_157)
        self.assertEqual(no_subject, 445)
        self.assertEqual(with_date, 574_496 + 2_704)
        self.assertEqual(attachments_lines_in_bodies, attachments_lines_in_blocks)


def count_attachments_lines(text: str) -> int:
    return sum(line.startswith("Attachments:") for line in text.split("\n"))


if __name__ == "__main__":
    unittest.main()

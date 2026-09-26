"""GMAIL-6: strip_quotes(body) removes the quoted earlier email and keeps what the author wrote.

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
from pipeline.gmail.quotes import StrippedBody, strip_quotes  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"


def kept(body: str) -> str:
    return strip_quotes(body).text


class WhereTheQuoteSits(unittest.TestCase):
    def test_quote_at_the_bottom(self):
        body = "Thanks Marissa.\n\nOn Sep 6, 2026, at 09:30, marissa_cole <marissa@redwood.com> wrote:\n> Claire — options below.\n> Term: 4 months."
        self.assertEqual(kept(body), "Thanks Marissa.")

    def test_quote_at_the_top_keeps_the_answer_below_it(self):
        body = (
            "On 2026-09-05 10:12, Claire Dawson wrote:\n> Thanks for the walkthrough earlier.\n> 1) Licensing model...\n\n"
            "Hi Claire — appreciate the details and the PDF.\n\n- Licensing recommendation: hybrid."
        )
        self.assertEqual(kept(body), "Hi Claire — appreciate the details and the PDF.\n\n- Licensing recommendation: hybrid.")

    def test_author_text_before_and_after_the_quote_is_kept(self):
        body = "Top line.\n\nOn Mon, May 10, 2027 at 08:23 Naomi Feldman <naomi@x.com> wrote:\n> old\n\nBottom line."
        self.assertEqual(kept(body), "Top line.\n\nBottom line.")

    def test_inline_answers_between_quoted_lines_are_kept(self):
        body = "> Is the fee credited?\nYes, 50% on the first invoice.\n> Is the term 4 months?\nYes."
        self.assertEqual(kept(body), "Yes, 50% on the first invoice.\nYes.")


class WhatCountsAsQuoted(unittest.TestCase):
    def test_both_opener_shapes(self):
        for opener in [
            "On Mon, May 10, 2027 at 08:23 Naomi Feldman <naomi@x.com> wrote:",
            "On 2026-09-05 10:12, Claire Dawson wrote:",
        ]:
            with self.subTest(opener=opener):
                self.assertEqual(kept(f"Reply.\n\n{opener}\n> old text"), "Reply.")

    def test_quoted_lines_without_an_opener_are_removed(self):
        self.assertEqual(kept("Reply.\n> old\n> older"), "Reply.")

    def test_a_quoted_opener_goes_with_its_quote(self):
        body = "Reply.\n> On Wed, 11 Feb 2026 at 09:12, Tom Rinaldi <t@x.com> wrote:\n> > deeper"
        self.assertEqual(kept(body), "Reply.")

    def test_nested_quotes_are_removed(self):
        self.assertEqual(kept("Reply.\n>> two\n> > three\n>>> four"), "Reply.")

    def test_quote_mark_with_no_space_is_still_a_quote(self):
        self.assertEqual(kept("Reply.\n>Jordan\n>Attachments: benchmark.csv"), "Reply.")

    def test_a_blank_line_between_opener_and_quote_is_allowed(self):
        self.assertEqual(kept("Reply.\n\nOn Tue, 11 Aug 2026 08:39:00 -0700, Sophie <s@x.com> wrote:\n\n> old"), "Reply.")

    def test_greater_than_inside_a_line_is_not_a_quote(self):
        body = "Latency a > b and x->y.\n >indented is not a quote mark\nDone."
        self.assertEqual(kept(body), body)

    def test_quoted_attachment_lines_go_but_the_authors_own_stay(self):
        body = "Attachments: mine.pdf\n\nOn Mon, 1 Jun 2026 at 10:00, A <a@x.com> wrote:\n> Attachments: theirs.pdf"
        self.assertEqual(kept(body), "Attachments: mine.pdf")


class OpenerVariations(unittest.TestCase):
    def test_a_leftover_escaped_carriage_return_after_the_opener(self):
        body = "Reply.\n\nOn Tue, Apr 10, 2028 at 15:20, kimberly_park wrote:\\r\n> old\n> older"
        self.assertEqual(kept(body), "Reply.")

    def test_a_short_note_after_the_opener(self):
        body = "Reply.\n\nOn Fri, Oct 9, 2026 at 11:50 AM Camila Reyes <c@x.com> wrote: (quoted below)\n> old"
        self.assertEqual(kept(body), "Reply.")

    def test_an_opener_with_a_note_but_no_quote_after_it_is_kept_and_flagged(self):
        body = "Reply.\n\nOn Fri, Oct 9, 2026 at 11:50 AM Camila Reyes <c@x.com> wrote: (quoted below)\nMore text."
        result = strip_quotes(body)
        self.assertEqual(result.text, body)
        self.assertTrue(result.opener_unmatched)

    def test_a_quote_on_the_same_line_as_the_opener_is_removed(self):
        line = "On Tue, 3 Mar 2026 at 10:00, Team <t@x.com> wrote: > Draft SOW attached."
        result = strip_quotes(f"Reply.\n\n{line}")
        self.assertEqual(result.text, "Reply.")
        self.assertEqual(result.quoted_chars, len(line) + 1)
        self.assertFalse(result.opener_unmatched)

    def test_a_greater_than_glued_to_a_quotation_mark_is_not_a_quote(self):
        body = 'On Sep 15, 2026, at 18:22, Sana <s@x.com> wrote:>" is how the header looks.\nDone.'
        self.assertEqual(strip_quotes(body), StrippedBody(body, 0, False))

    def test_a_lone_greater_than_after_the_opener_is_a_quote_mark(self):
        for line in ["On Sep 12, 2026, at 11:03 AM, Tessa Morgan wrote: >", "On Mon, Aug 16, 2027 at 09:00 Sofia <s@x.com> wrote:>"]:
            with self.subTest(line=line):
                self.assertEqual(kept(f"Reply.\n\n{line}"), "Reply.")

    def test_an_opener_pattern_quoted_inside_a_sentence_is_kept(self):
        body = 'On Tue, 3 Mar 2026 at 10:00, Sam wrote:" is how the header looks.\nDone.'
        self.assertEqual(strip_quotes(body), StrippedBody(body, 0, False))


class WhatIsLeftAlone(unittest.TestCase):
    def test_an_opener_with_no_quote_after_it_is_kept_and_flagged(self):
        body = "On Thu, 11 Jun 2026 at 08:39, Jonas Weber <j@x.com> wrote:\nTo: Sarah <s@x.com>\nSarah — thank you."
        self.assertEqual(strip_quotes(body), StrippedBody(body, 0, True))

    def test_lines_that_only_look_like_openers_are_kept(self):
        body = 'On quoting: "On Tue, Jul 28 Sofia wrote:" is the pattern.\nOn Tue, 10 Mar 2026 Vanessa wrote to execs: "escalate".'
        result = strip_quotes(body)
        self.assertEqual(result.text, body)
        self.assertFalse(result.opener_unmatched)

    def test_forward_marker_and_the_text_after_it_are_kept(self):
        body = "FYI below.\n\n--- Forwarded message ---\nSubject: Renewal terms\nThe terms are 12 months."
        self.assertEqual(kept(body), body)

    def test_original_message_marker_is_kept(self):
        body = "Reply.\n\n-----Original Message-----\nFrom: A <a@x.com>\nSent: Monday\nOld text."
        self.assertEqual(kept(body), body)

    def test_a_body_with_no_quoting_is_returned_unchanged(self):
        body = "Just an update.\n\n- one\n- two"
        self.assertEqual(strip_quotes(body), StrippedBody(body, 0, False))

    def test_trailing_spaces_are_tidied_whether_or_not_there_was_a_quote(self):
        self.assertEqual(strip_quotes("a  \nb"), StrippedBody("a\nb", 0, False))
        self.assertEqual(strip_quotes("a  \n> q\nb").text, "a\nb")

    def test_empty_body(self):
        self.assertEqual(strip_quotes(""), StrippedBody("", 0, False))


class WhatIsReported(unittest.TestCase):
    def test_a_body_that_is_only_a_quote_becomes_empty(self):
        result = strip_quotes("On 2026-09-05 10:12, Claire Dawson wrote:\n> everything\n> here")
        self.assertEqual(result.text, "")
        self.assertGreater(result.quoted_chars, 0)

    def test_quoted_chars_counts_every_removed_character(self):
        opener = "On 2026-09-05 10:12, Claire wrote:"
        self.assertEqual(strip_quotes(f"Hi\n{opener}\n> ab").quoted_chars, (len(opener) + 1) + (len("> ab") + 1))

    def test_blank_lines_left_by_a_removed_quote_are_collapsed(self):
        self.assertEqual(kept("One.\n\n> quoted\n\n\n\nTwo.\n"), "One.\n\nTwo.")

    def test_the_result_has_no_leading_or_trailing_newlines(self):
        self.assertEqual(kept("\n\nHi\n> q\n\n"), "Hi")


class Rerunning(unittest.TestCase):
    BODY = "Top.\n\nOn Mon, May 10, 2027 at 08:23 Naomi <n@x.com> wrote:\n> old\n\nBottom."

    def test_same_input_gives_same_output(self):
        self.assertEqual(strip_quotes(self.BODY), strip_quotes(self.BODY))

    def test_stripping_twice_changes_nothing(self):
        once = kept(self.BODY)
        self.assertEqual(kept(once), once)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        bodies = changed = empty_before = emptied_by_stripping = unmatched = quoted_chars = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            for block in split_messages(text).blocks:
                body = parse_headers(block).body
                result = strip_quotes(body)
                bodies += 1
                changed += result.text != body
                empty_before += not body
                emptied_by_stripping += bool(body) and not result.text
                unmatched += result.opener_unmatched
                quoted_chars += result.quoted_chars
                self.assertFalse(any(line.startswith(">") for line in result.text.split("\n")))
                self.assertEqual(strip_quotes(result.text).text, result.text)
        self.assertEqual(bodies, 578_443)
        # Every number below was counted first by a separately written script (plain string
        # checks, not this module), then compared with what strip_quotes returns.
        # Bodies with a ">" line (120,151) plus 137 with a quote on the opener line.
        self.assertEqual(changed, 120_288)
        # 780 bodies are only a quote; 723 more were already empty (headers only).
        self.assertEqual(emptied_by_stripping, 780)
        self.assertEqual(empty_before, 723)
        # 38,379,270 characters in ">" lines, the rest in removed openers and same-line quotes.
        self.assertEqual(quoted_chars, 45_457_656)
        # Bodies with an "On ... wrote:" line and no quote after it (kept, flagged).
        self.assertEqual(unmatched, 1_505)

if __name__ == "__main__":
    unittest.main()

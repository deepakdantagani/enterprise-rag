"""GMAIL-5a: normalise_date(raw) reads ISO and RFC 2822 dates into a UTC instant, the sender's offset and a flag.

Run: uv run python -m unittest discover tests
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail.cleaning import clean_thread  # noqa: E402
from pipeline.gmail.dates import NormalisedDate, normalise_date  # noqa: E402
from pipeline.gmail.headers import parse_headers  # noqa: E402
from pipeline.gmail.messages import split_messages  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"


def utc(raw: str) -> str:
    return normalise_date(raw).sent_at


def offset(raw: str):
    return normalise_date(raw).utc_offset_minutes


class IsoDates(unittest.TestCase):
    def test_iso_with_offset(self):
        self.assertEqual(
            normalise_date("2026-06-25T09:12:00-07:00"),
            NormalisedDate("2026-06-25T16:12:00+00:00", -420, False, "iso"),
        )

    def test_iso_with_z(self):
        self.assertEqual(
            normalise_date("2026-09-05T15:08:00Z"),
            NormalisedDate("2026-09-05T15:08:00+00:00", 0, False, "iso"),
        )

    def test_space_instead_of_t_and_no_seconds(self):
        self.assertEqual(
            normalise_date("2026-09-17 09:12 -0400"),
            NormalisedDate("2026-09-17T13:12:00+00:00", -240, False, "iso"),
        )

    def test_iso_without_a_zone_is_assumed_utc(self):
        self.assertEqual(
            normalise_date("2027-04-03 09:12"),
            NormalisedDate("2027-04-03T09:12:00+00:00", None, True, "iso"),
        )


class Rfc2822Dates(unittest.TestCase):
    def test_standard_offset(self):
        self.assertEqual(
            normalise_date("Thu, 25 Jun 2026 09:12:00 -0700"),
            NormalisedDate("2026-06-25T16:12:00+00:00", -420, False, "rfc2822"),
        )

    def test_colon_in_the_offset_keeps_its_zone(self):
        self.assertEqual(
            normalise_date("Thu, 25 Jun 2026 11:05:00 -07:00"),
            NormalisedDate("2026-06-25T18:05:00+00:00", -420, False, "rfc2822"),
        )

    def test_positive_offset_with_colon(self):
        self.assertEqual(utc("Mon, 24 May 2027 17:43:00 +01:00"), "2027-05-24T16:43:00+00:00")
        self.assertEqual(offset("Mon, 24 May 2027 17:43:00 +01:00"), 60)

    def test_plus_zero_is_a_real_zero_offset(self):
        self.assertEqual(offset("Wed, 14 Jul 2026 18:02:00 +0000"), 0)

    def test_minus_zero_is_utc_but_the_sender_zone_is_unknown(self):
        self.assertEqual(
            normalise_date("Tue, 20 Mar 2028 09:15:00 -0000"),
            NormalisedDate("2028-03-20T09:15:00+00:00", None, False, "rfc2822"),
        )

    def test_a_zone_comment_in_brackets_is_ignored(self):
        self.assertEqual(
            normalise_date("Sat, 7 Nov 2026 09:12:00 -0800 (PST)"),
            NormalisedDate("2026-11-07T17:12:00+00:00", -480, False, "rfc2822"),
        )

    def test_a_trailing_escaped_carriage_return_is_ignored(self):
        self.assertEqual(utc("Mon, 29 Jun 2026 09:12:00 -0700\\r"), "2026-06-29T16:12:00+00:00")
        self.assertEqual(utc("2026-10-22T08:12:00-07:00\\r"), "2026-10-22T15:12:00+00:00")


class NeverGuessesQuietly(unittest.TestCase):
    def test_a_day_that_does_not_exist_raises(self):
        with self.assertRaises(ValueError):
            normalise_date("Mon, 29 Feb 2027 07:30:00 -0800")

    def test_garbage_raises(self):
        for raw in ["not a date", "", "   "]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalise_date(raw)

    def test_a_date_with_no_time_of_day_raises(self):
        for raw in ["2026-06-25", "20260625"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalise_date(raw)

    def test_the_error_message_names_the_date_that_failed(self):
        for raw in ["Mon, 29 Feb 2027 07:30:00 -0800", "not a date"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as caught:
                    normalise_date(raw)
                self.assertIn(raw, str(caught.exception))

    def test_surrounding_spaces_are_ignored(self):
        self.assertEqual(utc("  2026-06-25T09:12:00-07:00 "), "2026-06-25T16:12:00+00:00")

    def test_same_input_gives_same_output(self):
        self.assertEqual(normalise_date("2026-09-17 09:12 -0400"), normalise_date("2026-09-17 09:12 -0400"))


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_date_counts(self):
        rules = Counter()
        unreadable = assumed = offset_unknown = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            for block in split_messages(text).blocks:
                date_raw = parse_headers(block).date_raw
                if not date_raw:
                    continue
                try:
                    result = normalise_date(date_raw)
                except ValueError:
                    unreadable += 1
                    continue
                rules[result.rule] += 1
                assumed += result.assumed_utc
                offset_unknown += result.utc_offset_minutes is None
                self.assertTrue(result.sent_at.endswith("+00:00"))
        self.assertEqual(rules, {"rfc2822": 414_691, "iso": 153_788})
        # 8,721 = the 8,595 Gmail-display dates GMAIL-5b reads, plus 126 that stay unreadable
        # (about 44 rare shapes, 12 bare dates, 14 days that do not exist such as 29 Feb 2027).
        self.assertEqual(unreadable, 8_721)
        self.assertEqual(assumed, 226)
        # 2,822 more end in -0000 (UTC, sender zone unknown).
        self.assertEqual(offset_unknown, 226 + 2_822)


if __name__ == "__main__":
    unittest.main()

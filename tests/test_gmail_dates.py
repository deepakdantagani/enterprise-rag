"""GMAIL-5a and 5b: normalise_date(raw) turns one Gmail date text into a UTC instant, the sender's offset and a flag.

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


class GmailDisplayDates(unittest.TestCase):
    def test_named_zone_after_am_pm(self):
        self.assertEqual(
            normalise_date("Thu, May 20, 2027 at 09:12 AM PDT"),
            NormalisedDate("2027-05-20T16:12:00+00:00", -420, False, "loose"),
        )
        self.assertEqual(utc("Tue, Feb 10, 2026 at 10:04 AM PST"), "2026-02-10T18:04:00+00:00")

    def test_24_hour_clock_with_a_named_zone(self):
        self.assertEqual(utc("Tue, May 25, 2027 at 16:08 EDT"), "2027-05-25T20:08:00+00:00")

    def test_named_zone_in_iso_shape(self):
        self.assertEqual(
            normalise_date("2026-11-15 13:12 UTC"),
            NormalisedDate("2026-11-15T13:12:00+00:00", 0, False, "loose"),
        )

    def test_am_pm_before_a_numeric_offset(self):
        self.assertEqual(utc("2027-04-18 09:12 AM -0700"), "2027-04-18T16:12:00+00:00")
        self.assertEqual(utc("Sun, Apr 4, 2027 at 3:12 PM -0700"), "2027-04-04T22:12:00+00:00")
        self.assertEqual(utc("Thu, Dec 2, 2026 at 9:12 AM -08:00"), "2026-12-02T17:12:00+00:00")

    def test_weekday_then_iso_date(self):
        self.assertEqual(utc("Mon, 2026-03-02 09:12:00 -0700"), "2026-03-02T16:12:00+00:00")

    def test_pm_is_not_dropped(self):
        result = normalise_date("Mon, Apr 28, 2025 4:40 PM")
        self.assertEqual(result, NormalisedDate("2025-04-28T16:40:00+00:00", None, True, "loose"))

    def test_am_pm_edges(self):
        self.assertEqual(utc("Mon, Apr 28, 2025 12:05 AM"), "2025-04-28T00:05:00+00:00")
        self.assertEqual(utc("Mon, Apr 28, 2025 12:30 PM"), "2025-04-28T12:30:00+00:00")

    def test_no_zone_at_all_is_assumed_utc(self):
        self.assertEqual(
            normalise_date("Fri, 25 Sep 2026 at 16:12"),
            NormalisedDate("2026-09-25T16:12:00+00:00", None, True, "loose"),
        )
        self.assertTrue(normalise_date("Thu, Apr 24, 2025 9:12 AM").assumed_utc)


class RealWorldVariations(unittest.TestCase):
    def test_full_weekday_and_month_names(self):
        self.assertEqual(
            normalise_date("Monday, June 10, 2028 9:12 AM"),
            NormalisedDate("2028-06-10T09:12:00+00:00", None, True, "loose"),
        )

    def test_no_comma_after_the_day(self):
        self.assertEqual(utc("Thu, Apr 29 2026 16:52:00 -0700"), "2026-04-29T23:52:00+00:00")

    def test_a_zone_comment_in_brackets_is_ignored(self):
        self.assertEqual(
            normalise_date("Sat, 7 Nov 2026 09:12:00 -0800 (PST)"),
            NormalisedDate("2026-11-07T17:12:00+00:00", -480, False, "rfc2822"),
        )

    def test_a_trailing_escaped_carriage_return_is_ignored(self):
        self.assertEqual(utc("Mon, 29 Jun 2026 09:12:00 -0700\\r"), "2026-06-29T16:12:00+00:00")
        self.assertEqual(utc("2026-10-22T08:12:00-07:00\\r"), "2026-10-22T15:12:00+00:00")

    def test_a_24_hour_time_followed_by_pm_is_read_as_24_hour(self):
        self.assertEqual(utc("2028-07-30 13:56 PM -0700"), "2028-07-30T20:56:00+00:00")

    def test_a_00_hour_followed_by_pm_stays_00(self):
        self.assertEqual(utc("2026-07-01 00:30 PM -0700"), "2026-07-01T07:30:00+00:00")

    def test_a_day_that_does_not_exist_raises(self):
        with self.assertRaises(ValueError):
            normalise_date("Mon, 29 Feb 2027 07:30:00 -0800")


class NamedZones(unittest.TestCase):
    def test_fixed_names(self):
        self.assertEqual(offset("2026-02-12 15:07 CET"), 60)
        self.assertEqual(offset("2026-07-12 15:07 CEST"), 120)
        self.assertEqual(offset("2026-07-12 15:07 EDT"), -240)
        self.assertEqual(offset("2026-01-12 15:07 EST"), -300)
        self.assertEqual(offset("2026-07-12 15:07 CDT"), -300)
        self.assertEqual(offset("2026-01-12 15:07 GMT"), 0)
        self.assertEqual(offset("2026-01-12 15:07 SGT"), 480)
        self.assertEqual(offset("2026-01-12 15:07 JST"), 540)

    def test_ambiguous_names_use_the_documented_reading(self):
        self.assertEqual(offset("2026-07-12 15:07 BST"), 60)
        self.assertEqual(offset("2026-07-12 15:07 IST"), 330)

    def test_pt_and_et_follow_summer_and_winter(self):
        self.assertEqual(offset("Thu, May 20, 2027 at 09:12 AM PT"), -420)
        self.assertEqual(offset("Tue, Feb 10, 2026 at 10:04 AM PT"), -480)
        self.assertEqual(offset("Thu, May 20, 2027 at 09:12 AM ET"), -240)
        self.assertEqual(offset("Tue, Feb 10, 2026 at 10:04 AM ET"), -300)
        self.assertEqual(utc("Tue, Feb 10, 2026 at 10:04 AM ET"), "2026-02-10T15:04:00+00:00")


class NeverGuessesQuietly(unittest.TestCase):
    def test_unknown_zone_name_raises(self):
        with self.assertRaises(ValueError):
            normalise_date("2026-02-12 15:07 XYZ")

    def test_garbage_raises(self):
        for raw in ["not a date", "", "   "]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalise_date(raw)

    def test_a_misspelled_month_or_weekday_raises(self):
        for raw in ["Sat, Marxxx 10, 2028 9:12 AM", "Foo, June 10, 2028 9:12 AM"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalise_date(raw)

    def test_month_names_full_short_and_sept(self):
        self.assertEqual(utc("Thursday, Sept 3, 2026 9:12 AM"), "2026-09-03T09:12:00+00:00")
        self.assertEqual(utc("Thu, 3 September 2026 at 09:12"), "2026-09-03T09:12:00+00:00")

    def test_a_date_with_no_time_of_day_raises(self):
        for raw in ["2026-06-25", "20260625"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalise_date(raw)

    def test_the_error_message_names_the_date_that_failed(self):
        for raw in ["Mon, 29 Feb 2027 07:30:00 -0800", "2026-02-12 15:07 XYZ", "not a date"]:
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
        failures = assumed = offset_unknown = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            for block in split_messages(text).blocks:
                date_raw = parse_headers(block).date_raw
                if not date_raw:
                    continue
                try:
                    result = normalise_date(date_raw)
                except ValueError:
                    failures += 1
                    continue
                rules[result.rule] += 1
                assumed += result.assumed_utc
                offset_unknown += result.utc_offset_minutes is None
                self.assertTrue(result.sent_at.endswith("+00:00"))
        # Measured: 126 dates (0.02%) still raise: about 44 rare shapes, 12 bare dates with no time of day
        # and 14 days that do not exist such as 29 Feb 2027. GMAIL-8 decides what a message with no readable date gets.
        self.assertEqual(failures, 126)
        self.assertEqual(rules, {"rfc2822": 414_691, "iso": 153_788, "loose": 8_595})
        self.assertEqual(assumed, 3_010)
        # 2,822 more end in -0000 (UTC, sender zone unknown).
        self.assertEqual(offset_unknown, 3_010 + 2_822)


if __name__ == "__main__":
    unittest.main()

"""GMAIL-8: message_records(filename, text) turns one clean thread into one flat record per message.

Run: uv run python -m unittest discover tests
"""
import dataclasses
import doctest
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail.cleaning import clean_thread  # noqa: E402
from pipeline.gmail import records as records_module  # noqa: E402
from pipeline.gmail.records import MessageRecord, message_records  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"

FILENAME = "dsid_000025680c494c78b8005828c90c9293__20260625-payment-orchestration-costpool-choreography.txt"
FIRST = (
    "From: Amal Khan <amal.khan@greenlinehealth.com>\n"
    "To: Vivek Kulkarni <vivek.kulkarni@redwood.ai>\n"
    "Cc: procure@greenlinehealth.com\n"
    "Date: Thu, 25 Jun 2026 09:12:00 -0700\n"
    "Subject: Invoice & VAT approach for multi-entity pilot (Greenline)\n"
    "\n"
    "Hi Vivek,\n"
    "Attachment: Greenline_PO_3042.pdf (application/pdf)"
)
SECOND = (
    "From: Vivek Kulkarni <vivek.kulkarni@redwood.ai>\n"
    "To: Amal Khan <amal.khan@greenlinehealth.com>\n"
    "Cc: Kimberly Park <kimberly_park@redwood.ai>, Marissa Cole <marissa_cole@redwood.ai>\n"
    "Date: Thu, 25 Jun 2026 11:05:00 -07:00\n"
    "Subject: Re: Invoice & VAT approach for multi-entity pilot (Greenline)\n"
    "\n"
    "Hi Amal, we can support both.\n"
    "\n"
    "On Thu, Jun 25, 2026 at 9:12 AM Amal Khan <amal.khan@greenlinehealth.com> wrote:\n"
    "> Hi Vivek,\n"
    "Attachment: entity_mapping_template.xlsx"
)
TITLE = "Payment orchestration: allocating regional seat charges across entities"
THREAD = f"{TITLE}\n\n{FIRST}\n\n{SECOND}\n"


class ThreadFields(unittest.TestCase):
    def test_one_record_per_message_in_file_order(self):
        records = message_records(FILENAME, THREAD)
        self.assertEqual([r.message_index for r in records], [0, 1])

    def test_dsid_and_thread_date_come_from_the_file_name(self):
        for record in message_records(FILENAME, THREAD):
            self.assertEqual(record.dsid, "dsid_000025680c494c78b8005828c90c9293")
            self.assertEqual(record.thread_date, "20260625")

    def test_thread_title_is_line_one_on_every_record(self):
        self.assertEqual({r.thread_title for r in message_records(FILENAME, THREAD)}, {TITLE})

    def test_a_file_date_that_is_not_a_real_day_is_kept_as_text(self):
        name = "dsid_8f12a9a90c414a2bbb9f64ed656846d3__20260229-promo-grant.txt"
        record = message_records(name, "T\n\nFrom: A <a@x.com>\nDate: 2026-02-27 09:00 -0000\n\nHi\n")[0]
        self.assertEqual(record.thread_date, "20260229")


class MessageFields(unittest.TestCase):
    def setUp(self):
        self.first, self.second = message_records(FILENAME, THREAD)

    def test_sender_recipients_subject(self):
        self.assertEqual(self.second.sender, "Vivek Kulkarni <vivek.kulkarni@redwood.ai>")
        self.assertEqual(
            self.second.recipients,
            ["Amal Khan <amal.khan@greenlinehealth.com>",
             "Kimberly Park <kimberly_park@redwood.ai>", "Marissa Cole <marissa_cole@redwood.ai>"],
        )
        self.assertEqual(self.second.subject, "Re: Invoice & VAT approach for multi-entity pilot (Greenline)")

    def test_recipients_are_to_then_cc(self):
        self.assertEqual(
            self.first.recipients,
            ["Vivek Kulkarni <vivek.kulkarni@redwood.ai>", "procure@greenlinehealth.com"],
        )

    def test_sent_at_is_utc(self):
        self.assertEqual(self.second.sent_at, "2026-06-25T18:05:00+00:00")
        self.assertFalse(self.second.date_missing)
        self.assertFalse(self.second.date_assumed_utc)

    def test_body_is_the_text_after_quotes_are_removed(self):
        self.assertEqual(self.second.body, "Hi Amal, we can support both.\n\nAttachment: entity_mapping_template.xlsx")
        self.assertNotIn("wrote:", self.second.body)

    def test_attachments_are_read_from_the_stripped_body(self):
        self.assertEqual(self.first.attachments, ["Greenline_PO_3042.pdf"])
        self.assertEqual(self.second.attachments, ["entity_mapping_template.xlsx"])

    def test_sha256_is_of_the_raw_block_before_any_rule_runs(self):
        self.assertEqual(self.second.sha256, hashlib.sha256(SECOND.encode("utf-8")).hexdigest())

    def test_a_clean_message_has_no_flags_set(self):
        self.assertEqual(
            (self.second.headers_missing, self.second.date_missing, self.second.date_assumed_utc, self.second.body_empty),
            (False, False, False, False),
        )


class AwkwardMessages(unittest.TestCase):
    def test_a_headerless_thread_gives_one_record_with_empty_fields_and_flags(self):
        name = "dsid_0070cd596374404085ed0cbca4e3a9e2__20280316-renewal.txt"
        (record,) = message_records(name, "Renewal paperwork\n\nJust some prose.\n")
        self.assertEqual((record.sender, record.recipients, record.subject), ("", [], ""))
        self.assertEqual(record.body, "Just some prose.")
        self.assertTrue(record.headers_missing)
        self.assertTrue(record.date_missing)
        self.assertEqual(record.sent_at, "")
        self.assertEqual(record.thread_date, "20280316")

    def test_headers_but_no_date_leaves_sent_at_empty(self):
        record = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nTo: B <b@y.com>\nSubject: s\n\nHi\n")[0]
        self.assertEqual((record.sent_at, record.date_missing, record.headers_missing), ("", True, False))

    def test_an_unreadable_date_leaves_sent_at_empty_and_does_not_raise(self):
        record = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nDate: Aug 30, 2025, 9:12 AM\n\nHi\n")[0]
        self.assertEqual((record.sent_at, record.date_missing), ("", True))

    def test_the_date_text_is_kept_so_unreadable_and_absent_dates_can_be_told_apart(self):
        unreadable = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nDate: Aug 30, 2025, 9:12 AM\n\nHi\n")[0]
        absent = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nSubject: s\n\nHi\n")[0]
        readable = message_records(FILENAME, THREAD)[1]
        self.assertEqual((unreadable.sent_at, unreadable.date_raw), ("", "Aug 30, 2025, 9:12 AM"))
        self.assertEqual((absent.sent_at, absent.date_raw), ("", ""))
        self.assertEqual(readable.date_raw, "Thu, 25 Jun 2026 11:05:00 -07:00")

    def test_a_date_with_no_zone_is_flagged_as_assumed_utc(self):
        record = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nDate: 2027-04-03 09:12\n\nHi\n")[0]
        self.assertEqual(record.sent_at, "2027-04-03T09:12:00+00:00")
        self.assertTrue(record.date_assumed_utc)
        self.assertFalse(record.date_missing)

    def test_a_message_emptied_by_quote_removal_is_kept_and_flagged(self):
        text = "T\n\nFrom: A <a@x.com>\nDate: 2027-04-03 09:12 -0000\n\n> old text\n> more\n"
        (record,) = message_records(FILENAME, text)
        self.assertEqual(record.body, "")
        self.assertTrue(record.body_empty)

    def test_a_message_with_no_text_at_all_is_kept_and_flagged(self):
        (record,) = message_records(FILENAME, "T\n\nFrom: A <a@x.com>\nDate: 2027-04-03 09:12 -0000\n")
        self.assertTrue(record.body_empty)

    def test_text_before_the_first_from_is_left_out(self):
        (record,) = message_records(FILENAME, "T\n\n--- Message 1 ---\n\nFrom: A <a@x.com>\n\nHi\n")
        self.assertEqual(record.body, "Hi")
        self.assertNotIn("Message 1", repr(record))

    def test_repeated_messages_are_all_kept_with_the_same_sha256(self):
        block = "From: A <a@x.com>\nDate: 2027-04-03 09:12 -0000\n\nSame\n"
        first, second = message_records(FILENAME, f"T\n\n{block}\n{block}")
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual((first.message_index, second.message_index), (0, 1))

    def test_message_index_is_file_order_even_when_dates_go_backwards(self):
        text = (
            "T\n\nFrom: A <a@x.com>\nDate: 2027-04-05 09:12 -0000\n\nlater\n\n"
            "From: B <b@y.com>\nDate: 2027-04-03 09:12 -0000\n\nearlier\n"
        )
        records = message_records(FILENAME, text)
        self.assertEqual([r.body for r in records], ["later", "earlier"])


class Shape(unittest.TestCase):
    def test_record_is_frozen_and_flat(self):
        record = message_records(FILENAME, THREAD)[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.sender = "x"
        for field in dataclasses.fields(MessageRecord):
            value = getattr(record, field.name)
            self.assertIsInstance(value, (str, int, bool, list), field.name)
            if isinstance(value, list):
                self.assertTrue(all(isinstance(item, str) for item in value), field.name)

    def test_field_names_are_the_contract(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(MessageRecord)],
            ["dsid", "thread_title", "thread_date", "message_index", "sender", "recipients", "sent_at", "date_raw",
             "subject", "attachments", "body", "sha256",
             "headers_missing", "date_missing", "date_assumed_utc", "body_empty"],
        )

    def test_same_input_gives_same_output(self):
        self.assertEqual(message_records(FILENAME, THREAD), message_records(FILENAME, THREAD))

    def test_the_module_docstring_example_runs(self):
        result = doctest.testmod(records_module)
        self.assertGreater(result.attempted, 0)
        self.assertEqual(result.failed, 0)

    def test_the_docstring_says_which_block_is_hashed(self):
        self.assertIn("as split_messages returns it", records_module.__doc__)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_record_counts(self):
        threads = records = headers_missing = date_missing = unreadable = assumed = body_empty = with_attachments = 0
        seen_ids = set()
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            thread_records = message_records(path.name, text)
            threads += 1
            self.assertGreaterEqual(len(thread_records), 1)
            self.assertEqual([r.message_index for r in thread_records], list(range(len(thread_records))))
            seen_ids.add(thread_records[0].dsid)
            for record in thread_records:
                records += 1
                headers_missing += record.headers_missing
                date_missing += record.date_missing
                assumed += record.date_assumed_utc
                body_empty += record.body_empty
                with_attachments += bool(record.attachments)
                self.assertEqual(bool(record.sent_at), not record.date_missing)
                unreadable += record.date_missing and bool(record.date_raw)
        # Measured by an independent scan (messages 578,443, not the story's 578,254).
        self.assertEqual((threads, len(seen_ids)), (121_390, 121_390))
        self.assertEqual(records, 578_443)
        self.assertEqual(headers_missing, 189)
        self.assertEqual(date_missing, 1_243 + 126)
        self.assertEqual(unreadable, 126)
        self.assertEqual(assumed, 3_010)
        self.assertEqual(body_empty, 1_503)
        self.assertEqual(with_attachments, 231_421)


if __name__ == "__main__":
    unittest.main()

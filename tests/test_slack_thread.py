"""SLACK-8: parse_thread(file_name, text) turns one clean thread into one Thread record.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import thread as thread_module  # noqa: E402
from pipeline.slack.channel import Channel  # noqa: E402
from pipeline.slack.speaker import Speaker  # noqa: E402
from pipeline.slack.thread import Message, Thread, parse_thread  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
NOVACARE = "dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-novacare-vra-check.txt"


class FileName(unittest.TestCase):
    def test_doc_id_and_slug_come_from_the_file_name(self):
        thread = parse_thread("dsid_00000f26be76466b9b871cb48ed51a28__1752467890-payment-amount-strings.txt", "eng\n\nkai: hi\n")
        self.assertEqual((thread.doc_id, thread.slug), ("00000f26be76466b9b871cb48ed51a28", "payment-amount-strings"))

    def test_a_file_name_without_a_slug(self):
        for name in ("dsid_5badc87efd7a49128d67b0234f809fa1__2987654321.txt",
                     "dsid_5bee63fa66544753a70f6a93bb0b848c__1859999999_1.txt"):
            self.assertIsNone(parse_thread(name, "eng\n\nkai: hi\n").slug, name)

    def test_a_slug_that_lost_its_dash_keeps_its_first_word(self):
        name = "dsid_ded5a06a70ae423694232825ed5c3f82__1931234000Region-fallback-and-burst-clarify.txt"
        self.assertEqual(parse_thread(name, "eng\n\nkai: hi\n").slug, "Region-fallback-and-burst-clarify")

    def test_the_timestamp_in_the_name_is_not_kept(self):
        self.assertEqual(Thread._fields, ("doc_id", "slug", "channel", "header", "messages", "participants"))

    def test_a_name_that_is_not_a_thread_file_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_thread("_manifest.json", "[]")


class Record(unittest.TestCase):
    TEXT = "customer-success\n\nAisha (CS): Hey team\nany takers?\n\nquestionnaire-bot: Received\n\nAisha (CS): thanks\n"

    def test_channel_header_and_messages(self):
        thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-x.txt", self.TEXT)
        self.assertEqual(thread.channel, Channel("customer-success", "line1"))
        self.assertEqual(thread.header, "customer-success\n\n")
        self.assertEqual(thread.messages, [
            Message(0, Speaker("Aisha", "CS", False), "Aisha (CS): Hey team\nany takers?\n\n"),
            Message(1, Speaker("questionnaire-bot", None, True), "questionnaire-bot: Received\n\n"),
            Message(2, Speaker("Aisha", "CS", False), "Aisha (CS): thanks\n"),
        ])

    def test_participants_are_distinct_names_in_the_order_they_first_speak(self):
        thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-x.txt", self.TEXT)
        self.assertEqual(thread.participants, ["Aisha", "questionnaire-bot"])

    def test_a_thread_with_no_speaker_line(self):
        thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1.txt", "general\n\njust a note\n")
        self.assertEqual((thread.header, thread.messages, thread.participants), ("general\n\njust a note\n", [], []))

    def test_header_and_message_texts_give_back_the_file_text(self):
        thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1.txt", self.TEXT)
        self.assertEqual(thread.header + "".join(message.text for message in thread.messages), self.TEXT)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(thread_module).failed, 0)


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_novacare(self):
        thread = parse_thread(NOVACARE, (CLEAN / NOVACARE).read_text(encoding="utf-8"))
        self.assertEqual((thread.doc_id, thread.slug, thread.channel.name, len(thread.messages)),
                         ("a4e702bd03254699b0e7bed0000972ab", "novacare-vra-check", "customer-success", 16))
        self.assertEqual(thread.participants, ["Aisha", "Priya", "Ben", "Tom", "questionnaire-bot"])
        self.assertEqual(thread.messages[4].speaker, Speaker("questionnaire-bot", None, True))

    def test_every_thread_parses_and_round_trips(self):
        totals, doc_ids = Counter(), set()
        for path in CLEAN.glob("*.txt"):
            text = path.read_text(encoding="utf-8")
            thread = parse_thread(path.name, text)
            self.assertEqual(thread.header + "".join(message.text for message in thread.messages), text, path.name)
            doc_ids.add(thread.doc_id)
            totals["threads"] += 1
            totals["messages"] += len(thread.messages)
            totals["without_slug"] += thread.slug is None
        self.assertEqual(totals, {"threads": 285_605, "messages": 5_741_020, "without_slug": 6_199})
        self.assertEqual(len(doc_ids), 285_605)


if __name__ == "__main__":
    unittest.main()

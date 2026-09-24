"""GMAIL-3: split_messages(text) cuts a clean Gmail thread into title, preamble and message blocks.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.gmail import messages as messages_module  # noqa: E402
from pipeline.gmail.cleaning import clean_thread  # noqa: E402
from pipeline.gmail.messages import SplitThread, split_messages  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"
THREAD = (
    "Renewal notes\n\n"
    "From: Ana <ana@x.com>\nTo: Raj <raj@x.com>\nDate: Mon, 1 Jun 2026 09:00:00 -0700\n\nHi Raj,\nCan we talk?\n\n"
    "From: Raj <raj@x.com>\nTo: Ana <ana@x.com>\nDate: Mon, 1 Jun 2026 10:00:00 -0700\n\nYes.\n"
)


def non_blank_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def rebuilt_non_blank_lines(split: SplitThread) -> list[str]:
    return non_blank_lines("\n".join([split.title, split.preamble, *split.blocks]))


class CuttingAtFrom(unittest.TestCase):
    def test_title_then_one_block_per_from_line(self):
        split = split_messages(THREAD)
        self.assertEqual(split.title, "Renewal notes")
        self.assertEqual(split.preamble, "")
        self.assertEqual(len(split.blocks), 2)

    def test_each_block_starts_with_from_and_has_no_trailing_blank_lines(self):
        first, second = split_messages(THREAD).blocks
        self.assertEqual(first, "From: Ana <ana@x.com>\nTo: Raj <raj@x.com>\nDate: Mon, 1 Jun 2026 09:00:00 -0700\n\nHi Raj,\nCan we talk?")
        self.assertTrue(second.startswith("From: Raj"))
        self.assertTrue(second.endswith("Yes."))

    def test_quoted_and_mid_line_from_do_not_start_a_block(self):
        text = "Title\n\nFrom: Ana <a@x.com>\n\n> From: Bob <b@x.com>\nsee From: the field\n  From: indented\n"
        self.assertEqual(len(split_messages(text).blocks), 1)

    def test_lines_between_title_and_first_from_are_kept_as_preamble(self):
        text = "Title\n\nDate: Thu, 15 Oct 2026 14:12:00 -0700\nFrom: Ana <a@x.com>\n\nHi\n"
        split = split_messages(text)
        self.assertEqual(split.preamble, "Date: Thu, 15 Oct 2026 14:12:00 -0700")
        self.assertEqual(split.blocks, ["From: Ana <a@x.com>\n\nHi"])


class ThreadsWithoutFrom(unittest.TestCase):
    def test_body_becomes_one_block_and_preamble_is_empty(self):
        split = split_messages("Re: Renewal\n\nHi Nikhil,\n\nThanks.\n")
        self.assertEqual(split, SplitThread(title="Re: Renewal", preamble="", blocks=["Hi Nikhil,\n\nThanks."]))

    def test_title_only_thread_has_no_blocks(self):
        self.assertEqual(split_messages("Just a title\n"), SplitThread("Just a title", "", []))

    def test_empty_text(self):
        self.assertEqual(split_messages(""), SplitThread("", "", []))


class NothingIsLost(unittest.TestCase):
    def test_every_non_blank_line_survives(self):
        for text in (THREAD, "T\n\nnote\nFrom: a\n\nx\n\nFrom: b\ny\n", "T\n\nno from here\n"):
            self.assertEqual(rebuilt_non_blank_lines(split_messages(text)), non_blank_lines(text))


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        from_blocks = whole_body_blocks = with_preamble = lost_lines = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            text = clean_thread(path.read_bytes().decode("utf-8")).text
            split = split_messages(text)
            starts_with_from = [block.startswith("From:") for block in split.blocks]
            from_blocks += sum(starts_with_from)
            whole_body_blocks += len(starts_with_from) - sum(starts_with_from)
            with_preamble += bool(split.preamble)
            lost_lines += rebuilt_non_blank_lines(split) != non_blank_lines(text)
        self.assertEqual(from_blocks, 578_254)
        self.assertEqual(whole_body_blocks, 189)
        self.assertEqual(with_preamble, 609)
        self.assertEqual(lost_lines, 0)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(messages_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

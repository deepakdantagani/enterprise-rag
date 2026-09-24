"""GMAIL-1a: clean_thread(raw) repairs a fully escaped Gmail thread and tidies whitespace only.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.cleaning import CleanResult, unescape  # noqa: E402
from pipeline.gmail import cleaning as cleaning_module  # noqa: E402
from pipeline.gmail.cleaning import clean_thread  # noqa: E402

RAW_DIR = ROOT / "data/gmail/raw"
ESCAPED_THREAD = (
    "Renewal notes\\n\\nFrom: Ana <ana@x.com>\\nTo: Raj <raj@x.com>\\n\\n"
    "Two asks:\\n- confirm sponsor\\n- pick a window\\n"
)


class EscapedThreads(unittest.TestCase):
    def test_escaped_thread_gets_real_newlines_and_is_flagged(self):
        result = clean_thread(ESCAPED_THREAD)
        self.assertEqual(
            result.text,
            "Renewal notes\n\nFrom: Ana <ana@x.com>\nTo: Raj <raj@x.com>\n\n"
            "Two asks:\n- confirm sponsor\n- pick a window\n",
        )
        self.assertTrue(result.was_escaped)

    def test_returns_the_shared_clean_result_type(self):
        self.assertIsInstance(clean_thread(ESCAPED_THREAD), CleanResult)


class PlainThreads(unittest.TestCase):
    def test_plain_thread_is_unchanged_and_not_flagged(self):
        text = "Title\n\nFrom: Ana <ana@x.com>\n\nHi there.\n"
        self.assertEqual(clean_thread(text), CleanResult(text=text, was_escaped=False))

    def test_a_single_printf_newline_is_not_unescaped(self):
        text = "Title\n\nFrom: Ana <ana@x.com>\n\nUse printf(\"%s\\n\") here.\nThanks.\n"
        result = clean_thread(text)
        self.assertEqual(result.text, text)
        self.assertFalse(result.was_escaped)

    def test_empty_thread_stays_empty(self):
        self.assertEqual(clean_thread(""), CleanResult(text="", was_escaped=False))


class OnlyWhitespaceIsTidied(unittest.TestCase):
    def test_bullet_never_becomes_a_heading(self):
        text = "Title\n\nFrom: Ana <ana@x.com>\n\nFiles:\n- draft_transfer_annex_notes.docx\n"
        self.assertEqual(clean_thread(text).text, text)

    def test_wiki_markup_is_left_alone(self):
        text = "Title\n\nh2. Scope\n||Name||Owner||\n"
        self.assertEqual(clean_thread(text).text, text)

    def test_trailing_spaces_removed(self):
        self.assertEqual(clean_thread("Title  \n\nBody \t\n").text, "Title\n\nBody\n")

    def test_runs_of_blank_lines_become_one(self):
        self.assertEqual(clean_thread("Title\n\n\n\nBody\n").text, "Title\n\nBody\n")

    def test_carriage_returns_become_newlines(self):
        self.assertEqual(clean_thread("Title\r\n\r\nBody\r\n").text, "Title\n\nBody\n")

    def test_text_ends_with_exactly_one_newline(self):
        self.assertEqual(clean_thread("Title\n\nBody").text, "Title\n\nBody\n")
        self.assertEqual(clean_thread("Title\n\nBody\n\n\n").text, "Title\n\nBody\n")

    def test_same_input_gives_same_output(self):
        self.assertEqual(clean_thread(ESCAPED_THREAD), clean_thread(ESCAPED_THREAD))

    def test_cleaning_twice_changes_nothing(self):
        once = clean_thread(ESCAPED_THREAD).text
        self.assertEqual(clean_thread(once).text, once)


class RealCorpus(unittest.TestCase):
    @unittest.skipUnless(RAW_DIR.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        escaped = ends_with_one_newline = with_from_line = new_heading_lines = 0
        for path in sorted(RAW_DIR.glob("*.txt")):
            raw = path.read_text(encoding="utf-8")
            result = clean_thread(raw)
            escaped += result.was_escaped
            ends_with_one_newline += result.text.endswith("\n") and not result.text.endswith("\n\n")
            if result.was_escaped:
                with_from_line += any(line.startswith("From:") for line in result.text.split("\n"))
                new_heading_lines += heading_lines(result.text) - heading_lines(unescape(raw))
        self.assertEqual(escaped, 27_870)
        self.assertEqual(ends_with_one_newline, 121_390)
        self.assertEqual(new_heading_lines, 0)
        # Measured, not yet explained: 11 escaped threads have no From: line even after unescaping.
        self.assertEqual(with_from_line, 27_859)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(cleaning_module).failed, 0)


def heading_lines(text: str) -> int:
    return sum(line.startswith("#") for line in text.split("\n"))


if __name__ == "__main__":
    unittest.main()

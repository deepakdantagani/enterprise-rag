import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.eval import ask_page  # noqa: E402
from pipeline.eval.ask_page import answer_html, benchmark_html, readable_opening, source_cards, tokens_with_ticks  # noqa: E402
from pipeline.eval.questions import Question  # noqa: E402

EDGEPATH = "dsid_85deb10a652742baaf28af6149600001"


class AnswerHtml(unittest.TestCase):
    def test_lines_starting_with_a_dash_become_a_list(self):
        self.assertEqual(answer_html("Redwood proposed:\n- ~40% off list\n- $50,000 credit"),
                         "<p>Redwood proposed:</p><ul><li>~40% off list</li><li>$50,000 credit</li></ul>")

    def test_star_bullets_and_bold_as_gemma4_writes_them(self):  # "What is Redwood Optimize?"
        self.assertEqual(answer_html("Key features:\n* **Core Levers:** batching"),
                         "<p>Key features:</p><ul><li><strong>Core Levers:</strong> batching</li></ul>")

    def test_text_is_escaped(self):
        self.assertEqual(answer_html("a <b> & c"), "<p>a &lt;b&gt; &amp; c</p>")


class ReadableOpening(unittest.TestCase):
    def test_a_gmail_thread_stored_as_a_list_string_reads_as_plain_text(self):
        raw = "['From: Sarah Lin <sarah.lin@edgepath.ai>\\nTo: Avery Johnson\\n\\nHi Avery,', 'From: Avery']"
        self.assertEqual(readable_opening(raw, 60), "From: Sarah Lin <sarah.lin@edgepath.ai> To: Avery Johnson Hi…")

    def test_a_doubly_escaped_line_break_leaves_no_backslash(self):  # dsid_6d658c67… (EdgeQuest)
        self.assertEqual(readable_opening("From: Lila\\\\nTo: Stephanie", 60), "From: Lila To: Stephanie")

    def test_short_text_is_kept_whole(self):
        self.assertEqual(readable_opening("Roll back the canary.", 60), "Roll back the canary.")


class SourceCards(unittest.TestCase):
    def test_the_list_opens_with_a_sources_heading_and_its_count(self):
        self.assertIn('<div class="rw-label">Sources · 1</div>', source_cards([("dsid_x", "slack", "T", "c")]))

    def test_no_documents_no_heading(self):
        self.assertEqual(source_cards([]), "")

    def test_one_card_per_document_numbered_with_source_title_id_and_opening(self):
        html = source_cards([(EDGEPATH, "gmail", "Licensing offsets & packaging", "From: Sarah Lin\nHi Avery,")])
        self.assertIn('<span class="rw-num">1</span>', html)
        self.assertIn('<span class="rw-src rw-src-gmail">Gmail</span>', html)
        self.assertIn("Licensing offsets &amp; packaging", html)
        self.assertIn(EDGEPATH, html)
        self.assertIn("From: Sarah Lin Hi Avery,", html)

    def test_an_unknown_source_still_gets_a_label(self):
        self.assertIn('<span class="rw-src rw-src-other">Document</span>', source_cards([("dsid_x", None, "T", "c")]))


class BenchmarkHtml(unittest.TestCase):
    def test_a_benchmark_question_shows_its_gold_answer_and_every_fact(self):
        question = Question("qst_0009", "basic", ("gmail",), "q?", (EDGEPATH,))
        html = benchmark_html(question, "Redwood proposed a 12-month package.", ["Fact one.", "Fact two."])
        self.assertIn("qst_0009", html)
        self.assertIn("Redwood proposed a 12-month package.", html)
        self.assertEqual(html.count("<li>"), 2)

    def test_a_new_question_shows_nothing(self):
        self.assertEqual(benchmark_html(None, "", []), "")


class TokensWithTicks(unittest.TestCase):
    def test_ticks_while_the_llm_is_silent_then_its_tokens_in_order(self):
        import time

        def slow():
            time.sleep(0.25)
            yield "Hello"
            yield " world"
        seen = list(tokens_with_ticks(slow, tick=0.1))
        self.assertIn(None, seen)
        self.assertEqual([token for token in seen if token is not None], ["Hello", " world"])


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(ask_page).failed, 0)


if __name__ == "__main__":
    unittest.main()

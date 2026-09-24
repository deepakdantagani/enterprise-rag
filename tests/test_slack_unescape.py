"""SLACK-1: unescape(text) turns a JSON-escaped Slack thread back into real characters.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import unescape as unescape_module  # noqa: E402
from pipeline.slack.unescape import UnescapeResult, is_escaped, unescape  # noqa: E402
from tools.slack_profile import read_thread_files  # noqa: E402

ARCHIVES = ROOT / "data/slack/archives"
MORNING_RIDDLE = "dsid_919525fd7c2944db922e298431b6e366__1814012345-morning-riddle-and-wfh-poll.txt"


class WhichFilesAreEscaped(unittest.TestCase):
    def test_body_on_one_line_with_a_literal_newline_is_escaped(self):
        self.assertTrue(is_escaped("general\n\nLena: hi\\nCarlos: yo"))

    def test_a_normal_thread_with_newline_inside_code_is_not_escaped(self):
        text = "eng\n\npaul: capture:```data: {}\\n\\n```\n\nkai: thanks"
        self.assertFalse(is_escaped(text))

    def test_an_escaped_backslash_before_n_is_not_a_newline(self):
        self.assertFalse(is_escaped("general\n\nsam: C:\\\\new"))
        self.assertTrue(is_escaped("general\n\nsam: C:\\\\\\new"))  # \\ then \n

    def test_a_final_newline_does_not_count_as_a_real_line_break(self):
        self.assertTrue(is_escaped("general\n\nLena: hi\\nCarlos: yo\n"))


class Unescape(unittest.TestCase):
    def test_newline(self):
        self.assertEqual(
            unescape("general\n\nLena: hi\\nCarlos: yo"),
            UnescapeResult("general\n\nLena: hi\nCarlos: yo", {"newline": 1}),
        )

    def test_quote(self):
        result = unescape('general\n\nLena: /poll \\"WFH\\"\\nRaj: ok')
        self.assertEqual(result.text, 'general\n\nLena: /poll "WFH"\nRaj: ok')
        self.assertEqual(result.rules_fired, {"newline": 1, "quote": 2})

    def test_tab_and_carriage_return(self):
        result = unescape("general\n\na:\\tb\\r\\nc: d")
        self.assertEqual(result.text, "general\n\na:\tb\r\nc: d")
        self.assertEqual(result.rules_fired, {"tab": 1, "carriage_return": 1, "newline": 1})

    def test_an_escaped_backslash_is_one_real_backslash_not_the_start_of_newline(self):
        result = unescape("general\n\nsam: C:\\\\new\\nkai: ok")
        self.assertEqual(result.text, "general\n\nsam: C:\\new\nkai: ok")
        self.assertEqual(result.rules_fired, {"backslash": 1, "newline": 1})

    def test_slash(self):
        result = unescape("general\n\nkai: see https:\\/\\/x.io\\nraj: ok")
        self.assertEqual(result.text, "general\n\nkai: see https://x.io\nraj: ok")
        self.assertEqual(result.rules_fired, {"slash": 2, "newline": 1})

    def test_unicode_and_a_surrogate_pair(self):
        result = unescape("general\n\nzoe: shoutout \\u2014 \\ud83d\\ude00\\nmaya: thanks")
        self.assertEqual(result.text, "general\n\nzoe: shoutout \u2014 \U0001F600\nmaya: thanks")
        self.assertEqual(result.rules_fired, {"unicode": 2, "newline": 1})

    def test_a_lone_surrogate_and_an_unknown_escape_stay_as_written(self):
        result = unescape("general\n\nbot: \\ud83d regex \\s+\\nkai: ok")
        self.assertEqual(result.text, "general\n\nbot: \\ud83d regex \\s+\nkai: ok")
        self.assertEqual(result.rules_fired, {"newline": 1})

    def test_a_thread_that_is_not_escaped_comes_back_byte_for_byte(self):
        text = 'sec\n\nsanjay: ```\ngcloud --member=\\"sa@x\\" \\\n  --role=r\n```\n\nkai: ok'
        self.assertEqual(unescape(text), UnescapeResult(text, {}))

    def test_a_high_surrogate_before_an_ordinary_escape(self):
        result = unescape("general\n\nbot: \\ud83d\\u2014\\nkai: ok")
        self.assertEqual(result.text, "general\n\nbot: \\ud83d\u2014\nkai: ok")

    def test_running_it_twice_changes_nothing_more(self):
        once = unescape("general\n\nLena: hi\\nCarlos: \\\\n is a newline")
        self.assertEqual(unescape(once.text), UnescapeResult(once.text, {}))
        single_message = unescape("general\n\nsam: C:\\\\new")
        self.assertEqual(single_message.rules_fired, {})

    def test_doctests(self):
        self.assertEqual(doctest.testmod(unescape_module).failed, 0)


@unittest.skipUnless(ARCHIVES.is_dir(), "Slack archives not present (data/ is gitignored)")
class RealCorpus(unittest.TestCase):
    def test_morning_riddle_gets_its_17_line_breaks_and_8_quotes(self):
        with zipfile.ZipFile(ARCHIVES / "slack_slice_0003.zip") as archive:
            raw = archive.read("slack/" + MORNING_RIDDLE).decode("utf-8")
        result = unescape(raw)
        self.assertEqual(result.rules_fired, {"newline": 17, "quote": 8})
        self.assertEqual(result.text.count("\n"), 2 + 17)

    def test_files_each_rule_fires_on(self):
        files_per_rule, files_changed = Counter(), 0
        for raw_bytes in read_thread_files(ARCHIVES):
            result = unescape(raw_bytes.decode("utf-8"))
            result.text.encode("utf-8")  # no lone surrogate may leak into the output
            files_changed += bool(result.rules_fired)
            files_per_rule.update(result.rules_fired.keys())
        self.assertEqual(files_changed, 8_334)
        self.assertEqual(files_per_rule, {
            "newline": 8_334, "quote": 4_083, "backslash": 787,
            "unicode": 147, "tab": 36, "carriage_return": 19, "slash": 14,
        })


if __name__ == "__main__":
    unittest.main()

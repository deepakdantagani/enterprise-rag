"""SLACK-2: normalize_whitespace(text) repairs whitespace without touching list or code indentation.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import whitespace as whitespace_module  # noqa: E402
from pipeline.slack.unescape import unescape  # noqa: E402
from pipeline.slack.whitespace import WhitespaceResult, normalize_whitespace  # noqa: E402
from tools.slack_profile import read_thread_files  # noqa: E402

ARCHIVES = ROOT / "data/slack/archives"


class IndentedSpeakerLines(unittest.TestCase):
    def test_an_indented_speaker_line_that_starts_a_message_is_straightened(self):
        result = normalize_whitespace("sales\n\njen_sales: Quick sync\n\n tom_ae: FYI customer claims\n")
        self.assertEqual(result.text, "sales\n\njen_sales: Quick sync\n\ntom_ae: FYI customer claims\n")
        self.assertEqual(result.rules_fired, {"indented_speaker": 1})

    def test_mid_message_it_is_straightened_only_if_the_name_speaks_twice(self):
        text = "eng\n\nkai: ok\n tom: first\n tom: second\n raj: once\n"
        self.assertEqual(normalize_whitespace(text).text, "eng\n\nkai: ok\ntom: first\ntom: second\n raj: once\n")

    def test_one_space_yaml_and_http_headers_keep_their_indent(self):
        text = "eng\n\nkai: config:\n enabled: true\n Host: api.redwood.example\n"
        self.assertEqual(normalize_whitespace(text), WhitespaceResult(text, {}))

    def test_a_tab_and_a_role_in_brackets(self):
        result = normalize_whitespace("eng\n\n\trina: ok\n\n dylan (finance): Draft MOU uploaded\n")
        self.assertEqual(result.text, "eng\n\nrina: ok\n\ndylan (finance): Draft MOU uploaded\n")

    def test_a_list_item_and_yaml_keep_their_indent(self):
        text = "eng\n\nben: plan:\n  - Verify SOC2 (owner: Ben)\n  max_retries: 5\n    enabled: true\n"
        self.assertEqual(normalize_whitespace(text), WhitespaceResult(text, {}))

    def test_anything_inside_a_code_fence_keeps_its_indent(self):
        text = "eng\n\nkai: logs:\n```\n tom_ae: not a speaker here\n```\n"
        self.assertEqual(normalize_whitespace(text), WhitespaceResult(text, {}))

    def test_a_fence_that_opens_mid_line_still_opens_a_block(self):
        text = "eng\n\nkai: logs:```\n tom: code\n```\n\n raj: hi\n"
        self.assertEqual(normalize_whitespace(text).text, "eng\n\nkai: logs:```\n tom: code\n```\n\nraj: hi\n")

    def test_an_unclosed_fence_keeps_the_rest_of_the_thread_as_code(self):
        text = "eng\n\nkai: logs:\n```\n\n tom: still code\n"
        self.assertEqual(normalize_whitespace(text), WhitespaceResult(text, {}))

    def test_an_inline_fence_on_one_line_does_not_open_a_block(self):
        result = normalize_whitespace("general\n\nlena: ```/poll \"WFH\"```\n\n raj: snacks\n")
        self.assertEqual(result.text, "general\n\nlena: ```/poll \"WFH\"```\n\nraj: snacks\n")


class OtherWhitespaceRules(unittest.TestCase):
    def test_carriage_returns_become_line_feeds(self):
        result = normalize_whitespace("eng\r\n\r\nkai: a\rb\n")
        self.assertEqual(result.text, "eng\n\nkai: a\nb\n")
        self.assertEqual(result.rules_fired, {"carriage_return": 3})

    def test_a_non_breaking_space_becomes_a_space(self):
        result = normalize_whitespace("eng\n\nkai: 5\u00a0GB\n")
        self.assertEqual(result, WhitespaceResult("eng\n\nkai: 5 GB\n", {"non_breaking_space": 1}))

    def test_trailing_whitespace_goes(self):
        result = normalize_whitespace("eng  \n\nkai: ok \t\n")
        self.assertEqual(result, WhitespaceResult("eng\n\nkai: ok\n", {"trailing_whitespace": 2}))

    def test_three_or_more_blank_lines_become_one(self):
        result = normalize_whitespace("eng\n\n\n\n\nkai: ok\n")
        self.assertEqual(result, WhitespaceResult("eng\n\nkai: ok\n", {"blank_line_run": 1}))

    def test_the_file_ends_with_exactly_one_newline(self):
        self.assertEqual(normalize_whitespace("eng\n\nkai: ok").text, "eng\n\nkai: ok\n")
        self.assertEqual(normalize_whitespace("eng\n\nkai: ok\n\n\n").text, "eng\n\nkai: ok\n")
        self.assertEqual(normalize_whitespace("eng\n\nkai: ok").rules_fired, {"final_newline": 1})

    def test_an_empty_thread_stays_empty(self):
        self.assertEqual(normalize_whitespace(""), WhitespaceResult("", {}))

    def test_running_it_twice_changes_nothing_more(self):
        once = normalize_whitespace(" \u00a0\r\n\n\n\n tom: hi  \r\n```\n  x \n```")
        self.assertEqual(normalize_whitespace(once.text), WhitespaceResult(once.text, {}))

    def test_doctests(self):
        self.assertEqual(doctest.testmod(whitespace_module).failed, 0)


@unittest.skipUnless(ARCHIVES.is_dir(), "Slack archives not present (data/ is gitignored)")
class RealCorpus(unittest.TestCase):
    def test_files_each_rule_fires_on_after_unescape(self):
        files_per_rule = Counter()
        for raw_bytes in read_thread_files(ARCHIVES):
            result = normalize_whitespace(unescape(raw_bytes.decode("utf-8")).text)
            files_per_rule.update(result.rules_fired.keys())
        self.assertEqual(files_per_rule, {
            "final_newline": 236_927, "trailing_whitespace": 66_893, "indented_speaker": 1_489,
            "blank_line_run": 476, "carriage_return": 269, "non_breaking_space": 55,
        })


if __name__ == "__main__":
    unittest.main()

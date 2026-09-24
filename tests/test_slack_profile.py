"""SLACK-0: profile(archives_dir, out_path) counts the Slack corpus straight from the zips.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import slack_profile  # noqa: E402
from tools.slack_profile import profile  # noqa: E402

ARCHIVES = ROOT / "data/slack/archives"


def make_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)


class Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        make_zip(self.tmp / "slice_0001.zip", {
            "slack/a.txt": "incidents\n\nmorgan: hi",
            "slack/b.txt": " incidents \n\nsanjay: ugh",
        })
        make_zip(self.tmp / "slice_0002.zip", {
            "slack/": "",
            "slack/c.txt": "1719998880\n\nElena: quick sync",
        })
        self.out = self.tmp / "profile.json"

    def test_counts_files_and_bytes_and_skips_non_txt_entries(self):
        result = profile(self.tmp, self.out)
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["bytes"], 21 + 24 + 29)

    def test_line1_words_are_listed_not_judged(self):
        result = profile(self.tmp, self.out)
        self.assertEqual(result["line1_channel_shaped"], {"incidents": 2})
        self.assertEqual(result["line1_other"], 1)

    def test_token_percentiles_use_four_chars_per_token(self):
        result = profile(self.tmp, self.out)
        self.assertEqual(result["tokens"], {"p50": 6, "p90": 7, "p99": 7, "max": 7})

    def test_writes_the_result_and_a_rerun_is_byte_identical(self):
        result = profile(self.tmp, self.out)
        first = self.out.read_bytes()
        self.assertEqual(json.loads(first), result)
        profile(self.tmp, self.out)
        self.assertEqual(self.out.read_bytes(), first)

    @unittest.skipUnless(ARCHIVES.is_dir(), "Slack archives not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        result = profile(ARCHIVES, self.out)
        self.assertEqual(result["files"], 285_605)
        self.assertEqual(result["bytes"], 964_465_933)
        self.assertEqual(len(result["line1_channel_shaped"]), 130)
        self.assertEqual(sum(result["line1_channel_shaped"].values()), 273_613)
        self.assertEqual(result["line1_other"], 11_992)
        self.assertEqual(result["line1_channel_shaped"]["incidents"], 24_044)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(slack_profile).failed, 0)


if __name__ == "__main__":
    unittest.main()

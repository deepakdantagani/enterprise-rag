"""GMAIL-0: profile(raw_dir, out_path) counts the Gmail corpus straight from data/gmail/raw.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import gmail_profile  # noqa: E402
from tools.gmail_profile import profile  # noqa: E402

RAW = ROOT / "data/gmail/raw"


def make_raw(dir_: Path, files: dict[str, str]) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (dir_ / name).write_text(text, encoding="utf-8")


FILES = {
    "a.txt": "Title\n\nFrom: a <a@x.com>\n\nhi there",
    "b.txt": "Title\\n\\nFrom: b <b@x.com>\\n\\nSome asks:\\n- one\\n- two",
    "c.txt": "Title\n\nprintf('%s\\n')\nmore\nlines\n",  # literal \n, but not escaped
    "d.txt": "Title\n\nNo header line here, just prose about a From: field",
}


class Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        make_raw(self.tmp, FILES)
        self.out = self.tmp / "profile.json"

    def test_counts_files_and_bytes(self):
        result = profile(self.tmp, self.out)
        self.assertEqual(result["files"], 4)
        self.assertEqual(result["bytes"], sum(len(text.encode()) for text in FILES.values()))

    def test_token_percentiles_use_four_chars_per_token(self):
        result = profile(self.tmp, self.out)
        chars = sorted(len(text) for text in FILES.values())  # [33, 34, 54, 58]
        self.assertEqual(result["tokens"]["max"], chars[-1] // 4)
        self.assertEqual(result["tokens"]["p50"], chars[1] // 4)

    def test_escape_counts_are_listed_not_judged(self):
        result = profile(self.tmp, self.out)
        # b.txt is properly escaped (6 literal \n, 0 real, so is_escaped says True).
        # c.txt has one literal \n but is genuine code (printf), so is_escaped says
        # False for it too: it lands in the ambiguous bucket, which is exactly the
        # point — this profiler does not decide printf-vs-partial-damage, GMAIL-1 does.
        self.assertEqual(result["literal_escape_files"], 2)  # b.txt, c.txt
        self.assertEqual(result["is_escaped_files"], 1)  # b.txt only
        self.assertEqual(result["ambiguous_escape_files"], 1)  # c.txt
        self.assertEqual(result["ambiguous_escape_files"],
                          result["literal_escape_files"] - result["is_escaped_files"])

    def test_from_header_must_start_a_line_real_or_escaped(self):
        result = profile(self.tmp, self.out)
        # d.txt has "From:" only mid-sentence, so it counts as no_from; a and b have a
        # line-starting From: (one real, one escaped); c has no From: line at all.
        self.assertEqual(result["no_from_files"], 2)  # c.txt, d.txt

    def test_writes_the_result_and_a_rerun_is_byte_identical(self):
        result = profile(self.tmp, self.out)
        first = self.out.read_bytes()
        self.assertEqual(json.loads(first), result)
        profile(self.tmp, self.out)
        self.assertEqual(self.out.read_bytes(), first)

    @unittest.skipUnless(RAW.is_dir(), "Gmail raw corpus not present (data/ is gitignored)")
    def test_real_corpus_counts(self):
        result = profile(RAW, self.out)
        self.assertEqual(result["files"], 121_390)
        self.assertEqual(result["literal_escape_files"], 28_049)  # matches design doc's damaged_threads
        self.assertEqual(result["is_escaped_files"], 27_870)
        self.assertEqual(result["ambiguous_escape_files"], 179)
        self.assertEqual(result["no_from_files"], 189)  # matches design doc's threads_without_from

    def test_doctests(self):
        self.assertEqual(doctest.testmod(gmail_profile).failed, 0)


if __name__ == "__main__":
    unittest.main()

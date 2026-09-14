"""PARSE-2a: clean_one_file(src, dst) reads one raw file, cleans it, writes one clean file.

Run: uv run python -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.cleaning import clean_text  # noqa: E402
from pipeline.corpus import clean_one_file  # noqa: E402

ESCAPED_RAW = "Title\n\nSummary:\\n\\n- one\\n- two\\n- three\\n- four\\n"


class CleanOneFile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "raw" / "page.txt"
        self.src.parent.mkdir()
        self.src.write_text(ESCAPED_RAW)

    def test_dst_contains_clean_text_of_src(self):
        dst = self.tmp / "clean" / "page.txt"
        dst.parent.mkdir()
        clean_one_file(self.src, dst)
        self.assertEqual(dst.read_text(), clean_text(ESCAPED_RAW).text)

    def test_return_value_reports_was_escaped(self):
        result = clean_one_file(self.src, self.tmp / "page.txt")
        self.assertTrue(result.was_escaped)

    def test_missing_dst_folder_is_created(self):
        dst = self.tmp / "does" / "not" / "exist" / "page.txt"
        clean_one_file(self.src, dst)
        self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()

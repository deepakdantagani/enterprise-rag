"""PARSE-2d: save_text and save_manifest, one job each (pipeline/corpus.py).

Run: uv run python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.corpus import save_manifest, save_text  # noqa: E402


class SaveText(unittest.TestCase):
    def test_creates_missing_folder_and_writes_exactly_the_text(self):
        path = Path(tempfile.mkdtemp()) / "does" / "not" / "exist" / "page.txt"
        save_text(path, "x\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "x\n")


class SaveManifest(unittest.TestCase):
    def test_rows_round_trip_through_manifest_json(self):
        clean_dir = Path(tempfile.mkdtemp())
        rows = [{"file": "a.txt", "clean_sha256": "1"}, {"file": "b.txt", "clean_sha256": "2"}]
        save_manifest(clean_dir, rows)
        self.assertEqual(json.loads((clean_dir / "_manifest.json").read_text()), rows)


class OneJobPerFunction(unittest.TestCase):
    def test_clean_one_file_is_gone_and_loop_has_no_json(self):
        source = (ROOT / "pipeline/corpus.py").read_text()
        self.assertNotIn("clean_one_file", source)
        loop = source[source.index("def write_clean_corpus"):]
        self.assertNotIn("json.", loop)


if __name__ == "__main__":
    unittest.main()

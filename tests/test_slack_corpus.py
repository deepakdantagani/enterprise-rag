"""SLACK-4: write_clean_corpus(archives_dir, clean_dir) cleans every thread once, with a manifest.

Run: uv run python -m unittest discover tests
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.observability import events_logged_to  # noqa: E402
from pipeline.slack.corpus import clean_thread, write_clean_corpus  # noqa: E402

ARCHIVES = ROOT / "data/slack/archives"
ESCAPED = "general\n\nLena: hi\\nCarlos: yo"
INDENTED = "sales\n\njen: sync  \n\n tom_ae: FYI\n"


def make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


class CleanThread(unittest.TestCase):
    def test_unescape_then_whitespace_with_the_rules_named_by_stage(self):
        text, rules = clean_thread(ESCAPED)
        self.assertEqual(text, "general\n\nLena: hi\nCarlos: yo\n")
        self.assertEqual(rules, {"unescape_newline": 1, "final_newline": 1})


class WriteCleanCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.archives = self.tmp / "archives"
        self.archives.mkdir()
        make_zip(self.archives / "slack_slice_0001.zip", {
            "slack/": b"",
            "slack/b.txt": INDENTED.encode(),
            "slack/a.txt": ESCAPED.encode(),
        })
        make_zip(self.archives / "slack_slice_0002.zip", {"slack/bad.txt": b"eng\n\n\xff\xfe"})
        self.clean = self.tmp / "clean"

    def test_writes_each_thread_under_its_own_name(self):
        write_clean_corpus(self.archives, self.clean)
        self.assertEqual((self.clean / "a.txt").read_text(), "general\n\nLena: hi\nCarlos: yo\n")
        self.assertEqual((self.clean / "b.txt").read_text(), "sales\n\njen: sync\n\ntom_ae: FYI\n")

    def test_the_manifest_has_one_row_per_cleaned_file_in_name_order(self):
        rows = write_clean_corpus(self.archives, self.clean)
        self.assertEqual([row["name"] for row in rows], ["a.txt", "b.txt"])
        self.assertEqual(rows[1], {
            "name": "b.txt",
            "raw_sha256": hashlib.sha256(INDENTED.encode()).hexdigest(),
            "clean_sha256": hashlib.sha256(b"sales\n\njen: sync\n\ntom_ae: FYI\n").hexdigest(),
            "rules": {"indented_speaker": 1, "trailing_whitespace": 1},
        })
        self.assertEqual(json.loads((self.clean / "_manifest.json").read_text()), rows)

    def test_a_file_that_fails_is_an_event_and_the_run_goes_on(self):
        log = self.tmp / "run.jsonl"
        with events_logged_to(log):
            rows = write_clean_corpus(self.archives, self.clean)
        events = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertFalse((self.clean / "bad.txt").exists())
        failed = [event for event in events if event["event"] == "FileFailed"]
        self.assertEqual([(event["file"], event["error_type"]) for event in failed],
                         [("bad.txt", "UnicodeDecodeError")])
        self.assertEqual(sum(event["event"] == "FileCleaned" for event in events), 2)
        stage_done = events[-1]
        self.assertEqual((stage_done["event"], stage_done["files"], stage_done["failed"]), ("StageDone", 2, 1))
        self.assertEqual(stage_done["source"], "slack")
        self.assertTrue(all("write_clean_corpus" in event["span_id"] for event in events))

    def test_logging_never_changes_the_output_and_a_rerun_is_identical(self):
        quiet = write_clean_corpus(self.archives, self.clean)
        with events_logged_to(self.tmp / "run.jsonl"):
            logged = write_clean_corpus(self.archives, self.clean)
        self.assertEqual(logged, quiet)


@unittest.skipUnless(ARCHIVES.is_dir(), "Slack archives not present (data/ is gitignored)")
class RealSlice(unittest.TestCase):
    def test_slice_0003_fingerprint(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "archives").mkdir()
        (tmp / "archives" / "slack_slice_0003.zip").symlink_to(ARCHIVES / "slack_slice_0003.zip")
        rows = write_clean_corpus(tmp / "archives", tmp / "clean")
        fingerprint = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        self.assertEqual(len(rows), 5_000)
        self.assertEqual(fingerprint, "27f964566403f03174e1d30718fdd0b1bab98ff661f8a75b9ecf17bb6aa99313")


if __name__ == "__main__":
    unittest.main()

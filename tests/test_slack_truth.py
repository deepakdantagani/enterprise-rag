"""SLACK-8b: parse_thread against 50 real threads whose message starts a reader decided.

tests/fixtures/slack_truth/ holds the threads (copied from data/slack/clean/, so this test
runs without the corpus) and expected.json, one entry per thread:

    why         the reason the thread was sampled
    starts      {line: [name, team_or_role, is_bot]} for every line where a message starts
    known_gaps  {line: {reason, parser_says}} where today's parser is knowingly wrong, and what it
                says there (null: it finds no start), so a gap that changes shape fails too

The starts were labelled blind: by readers who never saw the parser or its output. Every
disagreement with the parser was then checked by hand; in all 25 the reader was right, and
each is a known gap with its reason. SLACK-6b closed the 9 false starts; 16 remain.

Blind spot: the truth is per line, so a message that starts mid-line (one squashed thread
joins about 15 messages on two lines) cannot be marked, and the parser misses it too.

Run: uv run python -m unittest discover tests
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack.thread import Thread, parse_thread  # noqa: E402

TRUTH_DIR = ROOT / "tests/fixtures/slack_truth"
Start = tuple[str, str | None, bool]  # (name, team_or_role, is_bot)


def load_truth() -> dict[str, dict]:
    return json.loads((TRUTH_DIR / "expected.json").read_text(encoding="utf-8"))


def parsed_starts(thread: Thread) -> dict[int, Start]:
    """{line number: speaker} for every message start the parser found."""
    starts, line = {}, thread.header.count("\n") + 1
    for message in thread.messages:
        starts[line] = (message.speaker.name, message.speaker.team_or_role, message.speaker.is_bot)
        line += message.text.count("\n")
    return starts


def disagreements(parsed: dict[int, Start], truth: dict[int, Start]) -> set[int]:
    """Lines where the parser and the truth differ: a missed start, a false one, or other fields."""
    return {line for line in parsed.keys() | truth.keys() if parsed.get(line) != truth.get(line)}


def parse_fixture(name: str) -> Thread:
    return parse_thread(name, (TRUTH_DIR / name).read_text(encoding="utf-8"))


def truth_starts(entry: dict) -> dict[int, Start]:
    return {int(line): tuple(speaker) for line, speaker in entry["starts"].items()}


class TruthSet(unittest.TestCase):
    def test_the_parser_matches_every_hand_decided_start_except_the_known_gaps(self):
        for name, entry in load_truth().items():
            with self.subTest(name):
                parsed = parsed_starts(parse_fixture(name))
                self.assertEqual(disagreements(parsed, truth_starts(entry)), {int(line) for line in entry["known_gaps"]})
                for line, gap in entry["known_gaps"].items():
                    self.assertEqual(parsed.get(int(line)), tuple(gap["parser_says"]) if gap["parser_says"] else None, line)

    def test_the_truth_set_is_50_threads_and_862_starts(self):
        truth = load_truth()
        self.assertEqual(len(truth), 50)
        self.assertEqual(sum(len(entry["starts"]) for entry in truth.values()), 862)
        self.assertEqual({name for name in truth}, {path.name for path in TRUTH_DIR.glob("dsid_*.txt")})

    def test_precision_and_recall_of_message_starts(self):
        found = right = true = 0
        for name, entry in load_truth().items():
            parsed, truth = parsed_starts(parse_fixture(name)), truth_starts(entry)
            found, true, right = found + len(parsed), true + len(truth), right + len(parsed.keys() & truth.keys())
        self.assertEqual((found, true, right), (862, 862, 862))  # precision and recall 100% (871 found before SLACK-6b)

    def test_parsed_starts_on_a_small_thread(self):
        thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1.txt", "eng\n\nkai: a\nb\n\nbuild-bot: c\n")
        self.assertEqual(parsed_starts(thread), {3: ("kai", None, False), 6: ("build-bot", None, True)})


if __name__ == "__main__":
    unittest.main()

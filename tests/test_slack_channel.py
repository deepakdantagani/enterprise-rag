"""SLACK-5: channel_of(text) finds the channel of a clean Slack thread, and the route that found it.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import channel as channel_module  # noqa: E402
from pipeline.slack.channel import KNOWN_CHANNELS, Channel, channel_of  # noqa: E402

CLEAN = ROOT / "data/slack/clean"


class ChannelOf(unittest.TestCase):
    def test_line_1_is_a_known_channel(self):
        self.assertEqual(channel_of("customer-success\n\nAisha (CS): Hey team\n"),
                         Channel("customer-success", "line1"))

    def test_line_1_is_an_export_path(self):
        text = "sources/slack/eng-ml/3312349999-photon9b-int4-econ-flagging-guidance.json\n\nkai: ok\n"
        self.assertEqual(channel_of(text), Channel("eng-ml", "export_path"))

    def test_no_channel_anywhere(self):
        for first_line in ("1719998880", "2112345678-burst-header-backcompat-checkin.json",
                           "Elena: Quick sync", "", "kv-residency-sim-harness-sync"):
            with self.subTest(first_line=first_line):
                self.assertEqual(channel_of(first_line + "\n\nkai: ok\n"), Channel("unknown", "unknown"))

    def test_an_export_path_to_a_channel_nobody_uses_is_unknown(self):
        self.assertEqual(channel_of("sources/slack/my-topic/1.json\n\nkai: ok\n").route, "unknown")

    def test_a_channel_named_only_further_down_does_not_count(self):
        self.assertEqual(channel_of("1719998880\n\nkai: see sources/slack/incidents/1.json\n").name, "unknown")

    def test_there_are_36_known_channels(self):
        self.assertEqual(len(KNOWN_CHANNELS), 36)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(channel_module).failed, 0)


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_routes_and_channels_over_the_clean_corpus(self):
        routes, channels = Counter(), Counter()
        for path in CLEAN.glob("*.txt"):
            found = channel_of(path.read_text(encoding="utf-8"))
            routes[found.route] += 1
            channels[found.name] += 1
        self.assertEqual(routes, {"line1": 273_519, "export_path": 943, "unknown": 11_143})
        self.assertEqual(channels["incidents"], 24_044 + 120)
        self.assertEqual(channels["watercooler"], 3)


if __name__ == "__main__":
    unittest.main()

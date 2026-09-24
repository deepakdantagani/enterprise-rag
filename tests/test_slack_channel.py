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

    def test_line_1_is_an_export_path_with_or_without_sources(self):
        for first_line, channel in (
            ("sources/slack/eng-ml/3312349999-photon9b-int4-econ-flagging-guidance.json", "eng-ml"),
            ("slack/product/1842501234-keys-create-emptystate-presets-accessibility.json", "product"),
        ):
            with self.subTest(first_line=first_line):
                self.assertEqual(channel_of(first_line + "\n\nkai: ok\n"), Channel(channel, "export_path"))

    def test_no_channel_anywhere(self):
        for first_line in ("1719998880", "2112345678-burst-header-backcompat-checkin.json",
                           "Elena: Quick sync", "", "kv-residency-sim-harness-sync",
                           "sales-poc-benchmark"):
            with self.subTest(first_line=first_line):
                self.assertEqual(channel_of(first_line + "\n\nkai: ok\n"), Channel("unknown", "unknown"))

    def test_an_export_path_to_a_channel_nobody_uses_is_unknown(self):
        self.assertEqual(channel_of("sources/slack/my-topic/1.json\n\nkai: ok\n").route, "unknown")

    def test_a_channel_named_only_further_down_does_not_count(self):
        self.assertEqual(channel_of("1719998880\n\nkai: see sources/slack/incidents/1.json\n").name, "unknown")

    def test_line_1_is_matched_exactly_after_trimming(self):
        self.assertEqual(channel_of("incidents\r\n\r\nkai: ok").name, "incidents")
        for first_line in ("Incidents", "#incidents", "\ufeffincidents"):  # none occur in the corpus
            with self.subTest(first_line=first_line):
                self.assertEqual(channel_of(first_line + "\n\nkai: ok").name, "unknown")

    def test_there_are_35_known_channels(self):
        self.assertEqual(len(KNOWN_CHANNELS), 35)

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
        self.assertEqual(routes, {"line1": 273_516, "export_path": 3_036, "unknown": 9_053})
        self.assertEqual(channels, {
            "incidents": 24_226, "eng-platform": 23_308, "eng-runtime": 21_830, "eng-ml": 17_269,
            "product": 16_146, "support": 15_866, "eng-releases": 15_354, "customer-success": 13_926,
            "sales": 12_669, "eng-infra": 12_440, "eng-security": 12_429, "devex": 12_379,
            "marketing": 9_929, "docs": 9_556, "unknown": 9_053, "eng-oncall": 8_529,
            "partnerships": 8_462, "people-ops": 7_382, "architecture": 5_711, "finance": 5_216,
            "random": 4_109, "design": 3_785, "new-hires": 3_378, "eng-sre": 3_369,
            "all-hands": 3_357, "eng": 1_618, "announcements": 1_550, "vendors": 1_071,
            "lunch-plans": 629, "postmortems": 565, "general": 359, "help": 74,
            "release-war-room": 36, "sports": 15, "memes": 7, "watercooler": 3,
        })


if __name__ == "__main__":
    unittest.main()

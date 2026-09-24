"""SLACK-7: parse_speaker(line) reads name, team or role, and bot flag off a message's speaker line.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import speaker as speaker_module  # noqa: E402
from pipeline.slack.messages import split_messages  # noqa: E402
from pipeline.slack.speaker import Speaker, bot_rule, parse_speaker  # noqa: E402

CLEAN = ROOT / "data/slack/clean"


class ParseSpeaker(unittest.TestCase):
    def test_a_name_alone(self):
        self.assertEqual(parse_speaker("tom_ae: FYI customer claims"), Speaker("tom_ae", None, False))

    def test_what_is_in_brackets(self):
        self.assertEqual(parse_speaker("Aisha (CS): Hey team"), Speaker("Aisha", "CS", False))

    def test_what_is_after_a_dash(self):
        self.assertEqual(parse_speaker("Ruth - Customer Success: Quick sync"),
                         Speaker("Ruth", "Customer Success", False))

    def test_brackets_win_over_a_dash(self):
        self.assertEqual(parse_speaker("Dan - HelixEdge (SI): Were ready to support initial customers."),
                         Speaker("Dan", "SI", False))

    def test_a_team_first_line_is_read_as_written(self):
        self.assertEqual(parse_speaker("Legal - Priya: I'll handle the publisher agreement"),
                         Speaker("Legal", "Priya", False))

    def test_naming_styles_are_kept_as_written(self):
        names = [parse_speaker(line).name for line in ("jen_sales: a", "alex-cust: b", "Maya Chen: c", "Priya S.: d")]
        self.assertEqual(names, ["jen_sales", "alex-cust", "Maya Chen", "Priya S."])

    def test_bots_by_name(self):
        lines = ["questionnaire-bot: Received", "Incident Bot: SEV2", "DeployBot: done", "deploybot: done", "bot-ci: green",
                 "bot_deploy: note: open-embed-v1 variant rollout"]
        self.assertEqual([parse_speaker(line).is_bot for line in lines], [True] * 6)

    def test_a_bot_by_its_team_or_role(self):
        self.assertEqual(parse_speaker("evi (bot): :eyes: Good job team."), Speaker("evi", "bot", True))
        self.assertTrue(parse_speaker("Front Desk (Bot): Lunch is here").is_bot)

    def test_people_whose_names_only_contain_bot_are_not_bots(self):
        self.assertEqual([parse_speaker(line).is_bot for line in ("Botty: hi", "both: ok")], [False, False])

    def test_a_whole_message_works_as_well_as_its_first_line(self):
        self.assertEqual(parse_speaker("Aisha (CS): Hey team\nCan someone pick this up?\n"), Speaker("Aisha", "CS", False))

    def test_a_line_that_is_not_a_speaker_line_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_speaker("- Verify SOC2")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(speaker_module).failed, 0)


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_every_message_has_a_speaker_and_each_bot_rule_is_pinned(self):
        totals, messages_per_bot_rule = Counter(), Counter()
        for path in CLEAN.glob("*.txt"):
            for message in split_messages(path.read_text(encoding="utf-8")).messages:
                speaker = parse_speaker(message)
                totals["messages"] += 1
                totals["with_team_or_role"] += speaker.team_or_role is not None
                totals["from_bots"] += speaker.is_bot
                messages_per_bot_rule[bot_rule(speaker.name, speaker.team_or_role)] += 1
        self.assertEqual(totals, {"messages": 5_741_020, "with_team_or_role": 762_083, "from_bots": 573_797})
        del messages_per_bot_rule[None]
        self.assertEqual(messages_per_bot_rule,
                         {"name_ends_in_bot": 573_157, "name_starts_with_bot": 444, "team_or_role_is_bot": 196})


if __name__ == "__main__":
    unittest.main()

"""SLACK-6: split_messages(text) cuts a clean Slack thread into its messages.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import messages as messages_module  # noqa: E402
from pipeline.slack.messages import Split, split_messages  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
NOVACARE = "dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-novacare-vra-check.txt"


class SplitMessages(unittest.TestCase):
    def test_blank_line_layout_keeps_a_continuation_line_in_its_message(self):
        text = "customer-success\n\nAisha (CS): Hey team\nCan someone pick this up?\n\nPriya (Onboarding): I can.\n"
        self.assertEqual(split_messages(text), Split(
            header="customer-success\n\n",
            messages=["Aisha (CS): Hey team\nCan someone pick this up?\n\n", "Priya (Onboarding): I can.\n"],
        ))

    def test_one_message_per_line_layout(self):
        text = "1772201234-llm-cafe-antics.json\n\nsam: coffee?\nmaya: yes\ndeploy-bot: done\n"
        self.assertEqual(split_messages(text).messages, ["sam: coffee?\n", "maya: yes\n", "deploy-bot: done\n"])

    def test_a_blank_line_and_a_speaker_shape_inside_a_code_block_stay_in_one_message(self):
        text = "eng\n\nkai: logs:```\nstep 1\n\nraj: not a speaker here\n```\n\nraj: thanks\n"
        self.assertEqual(split_messages(text).messages,
                         ["kai: logs:```\nstep 1\n\nraj: not a speaker here\n```\n\n", "raj: thanks\n"])

    def test_labels_are_not_speakers(self):
        text = "eng\n\npriya: Added tasks:\n- Verify SOC2\nDue: 2026-04-02\nNote: owner is Ben\nContent-Type: application/json\n"
        self.assertEqual(len(split_messages(text).messages), 1)

    def test_full_names_are_speakers_and_a_labelled_plan_is_not(self):
        text = "eng\n\nMaya Chen: ok\nPriya S.: fine\nConnor O'Brien: agreed\nPlan B: roll back\n"
        self.assertEqual(len(split_messages(text).messages), 3)

    def test_team_handles_are_speakers(self):
        text = "eng\n\nkai: paging\nops: on it\nlegal: fine by us\n"
        self.assertEqual(len(split_messages(text).messages), 3)

    def test_a_speaker_on_line_1_is_the_first_message_and_the_header_is_empty(self):
        self.assertEqual(split_messages("Elena: Quick sync\nkai: ok\n"),
                         Split(header="", messages=["Elena: Quick sync\n", "kai: ok\n"]))

    def test_a_thread_with_no_speaker_is_all_header(self):
        self.assertEqual(split_messages("general\n\njust a note\n"), Split("general\n\njust a note\n", []))

    def test_joining_header_and_messages_gives_back_the_input(self):
        text = "eng\n\nkai: a\n\n\nraj: b\nNote: c"
        split = split_messages(text)
        self.assertEqual(split.header + "".join(split.messages), text)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(messages_module).failed, 0)


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_novacare_has_16_messages_and_priyas_task_list_is_one_of_them(self):
        split = split_messages((CLEAN / NOVACARE).read_text(encoding="utf-8"))
        self.assertEqual(split.header, "customer-success\n\n")
        self.assertEqual(len(split.messages), 16)
        self.assertIn("Due: 2026-04-02", split.messages[8])

    def test_corpus_totals_and_every_thread_round_trips(self):
        totals = Counter()
        for path in CLEAN.glob("*.txt"):
            text = path.read_text(encoding="utf-8")
            split = split_messages(text)
            self.assertEqual(split.header + "".join(split.messages), text, path.name)
            totals["threads"] += 1
            totals["messages"] += len(split.messages)
            totals["threads_without_messages"] += not split.messages
        self.assertEqual(totals, {"threads": 285_605, "messages": 5_687_671, "threads_without_messages": 88})


if __name__ == "__main__":
    unittest.main()

"""GEN-9g: every v3 answer judged on gpt-5.4."""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.eval import gpt_judge  # noqa: E402
from pipeline.eval.gpt_judge import GPT_ALL, not_judged  # noqa: E402
from pipeline.eval.rerank import read_jsonl  # noqa: E402


class NotJudged(unittest.TestCase):
    ROW = not_judged({"question_id": "qst_0351", "answer_facts": ["Fetch the rollout step.", "Pause the rollout."]})

    def test_an_empty_answer_is_wrong_and_zero_percent_complete(self):
        self.assertEqual((self.ROW["question_id"], self.ROW["answer_correct"], self.ROW["completeness_pct"]),
                         ("qst_0351", False, 0.0))

    def test_every_fact_is_kept_as_not_contained(self):
        self.assertEqual(self.ROW["facts"], [{"fact": "Fetch the rollout step.", "contained": False},
                                             {"fact": "Pause the rollout.", "contained": False}])

    def test_the_reason_says_it_was_not_judged(self):
        self.assertTrue(self.ROW["reason"].startswith("Not judged: the answer is empty."))


class Files(unittest.TestCase):
    def test_the_judgments_file_names_the_answers_and_the_judge(self):
        self.assertEqual(GPT_ALL.name, "v4-deepseek-v4-pro-v3__gpt-5.4.jsonl")


@unittest.skipUnless(GPT_ALL.is_file(), "the gpt-5.4 judgments are not on this machine")
class RealJudgments(unittest.TestCase):
    def test_500_questions_each_judged_once(self):
        rows = read_jsonl(GPT_ALL)
        self.assertEqual((len(rows), len({row["question_id"] for row in rows})), (500, 500))

    def test_the_three_empty_answers_are_the_only_ones_not_judged(self):
        self.assertEqual(sorted(row["question_id"] for row in read_jsonl(GPT_ALL) if row["reason"].startswith("Not judged")),
                         ["qst_0351", "qst_0358", "qst_0362"])


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(gpt_judge).failed, 0)


if __name__ == "__main__":
    unittest.main()

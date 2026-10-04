"""GEN-9f: the 100-question sample and the agreement of two judges on it."""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.eval import judge, judge_agreement  # noqa: E402
from pipeline.eval.judge_agreement import GPT_JUDGMENTS, OUR_JUDGMENTS, agreement, sample_ids  # noqa: E402
from pipeline.eval.rerank import read_jsonl  # noqa: E402


def questions(basic, semantic):
    return ([{"question_id": f"b{n:02}", "question_type": "basic"} for n in range(basic)]
            + [{"question_id": f"s{n:02}", "question_type": "semantic"} for n in range(semantic)])


class SampleIds(unittest.TestCase):
    def test_each_type_keeps_its_share(self):
        picked = sample_ids(questions(30, 10), count=8)
        self.assertEqual((sum(q.startswith("b") for q in picked), sum(q.startswith("s") for q in picked)), (6, 2))

    def test_the_same_seed_gives_the_same_sample_whatever_the_order_of_the_questions(self):
        self.assertEqual(sample_ids(questions(30, 10), count=8), sample_ids(questions(30, 10)[::-1], count=8))

    def test_another_seed_gives_another_sample(self):
        self.assertNotEqual(sample_ids(questions(30, 10), count=8), sample_ids(questions(30, 10), count=8, seed=1))

    def test_a_question_without_an_answer_is_never_picked(self):
        picked = sample_ids(questions(4, 4), count=4, skip={"b00", "b01"})
        self.assertEqual([q for q in picked if q.startswith("b")], ["b02", "b03"])

    def test_the_sample_is_sorted_by_question_id(self):
        picked = sample_ids(questions(30, 10), count=8)
        self.assertEqual(picked, sorted(picked))


def row(question_id, correct, contained):
    return {"question_id": question_id, "answer_correct": correct,
            "completeness_pct": round(100 * sum(contained) / len(contained), 2),
            "facts": [{"fact": f"fact {n}", "contained": found} for n, found in enumerate(contained)]}


class Agreement(unittest.TestCase):
    OURS = [row("q1", True, [True, True]), row("q2", True, [True, False]), row("q3", False, [False, False])]
    THEIRS = [row("q1", True, [True, True]), row("q2", False, [True, True]), row("q3", False, [False, False])]

    def test_correctness_agreement_is_the_share_of_questions_with_the_same_verdict(self):
        self.assertEqual(agreement(self.OURS, self.THEIRS)["correct_agreement"], 0.6667)

    def test_fact_agreement_counts_every_fact_once(self):
        self.assertEqual(agreement(self.OURS, self.THEIRS)["fact_agreement"], 0.8333)  # 5 of 6 facts

    def test_both_overall_scores_are_on_the_same_questions(self):
        found = agreement(self.OURS, self.THEIRS)
        self.assertEqual((found["questions"], found["score_ours"], found["score_theirs"]), (3, 50.0, 33.33))

    def test_each_disagreement_names_the_question_and_both_verdicts(self):
        self.assertEqual(agreement(self.OURS, self.THEIRS)["disagreements"],
                         [{"question_id": "q2", "ours": True, "theirs": False}])

    def test_only_questions_judged_by_both_are_compared(self):
        self.assertEqual(agreement(self.OURS, self.THEIRS[:1])["questions"], 1)


class JudgeModel(unittest.TestCase):
    def test_a_gpt_model_is_judged_on_openai_and_any_other_on_anthropic(self):
        self.assertEqual((type(judge.judge_llm("gpt-5.4")).__name__, type(judge.judge_llm("claude-haiku-4-5")).__name__),
                         ("OpenAI", "Anthropic"))

    def test_the_official_judge_is_gpt_5_4(self):
        self.assertEqual(judge_agreement.OFFICIAL_JUDGE, "gpt-5.4")


@unittest.skipUnless(GPT_JUDGMENTS.is_file(), "the gpt-5.4 judgments are not on this machine")
class RealAgreement(unittest.TestCase):
    def test_100_questions_judged_by_both(self):
        self.assertEqual(agreement(read_jsonl(OUR_JUDGMENTS), read_jsonl(GPT_JUDGMENTS))["questions"], 100)


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(judge_agreement).failed, 0)


if __name__ == "__main__":
    unittest.main()

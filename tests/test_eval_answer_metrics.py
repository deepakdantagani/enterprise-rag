"""GEN-11a: answer_rows, the judged answers of one run as metrics.json rows, overall and per source.

Run: uv run python -m unittest tests.test_eval_answer_metrics
"""
import doctest
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import answer_metrics  # noqa: E402
from pipeline.eval.answer_metrics import METRICS, answer_rows  # noqa: E402

QUESTIONS = [{"question_id": "q1", "question_type": "basic", "source_types": ["slack"]},
             {"question_id": "q2", "question_type": "semantic", "source_types": ["slack", "jira"]},
             {"question_id": "q3", "question_type": "basic", "source_types": []}]
JUDGMENTS = [{"question_id": "q1", "answer_correct": True, "completeness_pct": 100.0},
             {"question_id": "q2", "answer_correct": False, "completeness_pct": 50.0},
             {"question_id": "q3", "answer_correct": True, "completeness_pct": 80.0}]


class AnswerRows(unittest.TestCase):
    def setUp(self):
        self.rows = {row["group"]: row for row in answer_rows(QUESTIONS, JUDGMENTS)}

    def test_overall_is_every_question(self):
        self.assertEqual(self.rows["overall"], {"group": "overall", "questions": 3, "means": {
            "correct": 2 / 3, "completeness": (100 + 50 + 80) / 300, "score": (100 + 0 + 80) / 300}})

    def test_a_wrong_answer_scores_zero_but_keeps_its_completeness(self):
        self.assertEqual(self.rows["source:jira"]["means"], {"correct": 0.0, "completeness": 0.5, "score": 0.0})

    def test_a_question_counts_under_every_source_of_its_expected_documents(self):
        self.assertEqual((self.rows["source:slack"]["questions"], self.rows["source:jira"]["questions"]), (2, 1))

    def test_questions_with_no_expected_document_get_their_own_group(self):
        self.assertEqual(self.rows["source:none"], {"group": "source:none", "questions": 1, "means": {
            "correct": 1.0, "completeness": 0.8, "score": 0.8}})

    def test_the_groups_are_overall_then_each_source_then_each_question_type(self):
        self.assertEqual([row["group"] for row in answer_rows(QUESTIONS, JUDGMENTS)],
                         ["overall", "source:jira", "source:none", "source:slack", "type:basic", "type:semantic"])

    def test_a_question_counts_under_its_one_question_type(self):
        self.assertEqual(self.rows["type:basic"], {"group": "type:basic", "questions": 2, "means": {
            "correct": 1.0, "completeness": 0.9, "score": 0.9}})
        self.assertEqual(self.rows["type:semantic"]["means"], {"correct": 0.0, "completeness": 0.5, "score": 0.0})

    def test_a_question_that_was_not_judged_fails_loudly(self):
        with self.assertRaises(KeyError):
            answer_rows(QUESTIONS, JUDGMENTS[:2])


@unittest.skipUnless((answer_metrics.RUN / "metrics.json").is_file(), "no answer metrics yet")
class RealV2Answers(unittest.TestCase):
    def setUp(self):
        saved = json.loads((answer_metrics.RUN / "metrics.json").read_text())
        self.config, self.rows = saved["config"], {row["group"]: row for row in saved["rows"]}

    def test_overall_is_62_43_over_500_questions(self):
        overall = self.rows["overall"]
        self.assertEqual((overall["questions"], round(overall["means"]["score"] * 100, 2),
                          round(overall["means"]["correct"] * 500)), (500, 62.43, 345))

    def test_confluence_is_the_largest_and_weakest_source(self):
        confluence = self.rows["source:confluence"]
        self.assertEqual((confluence["questions"], round(confluence["means"]["score"] * 100, 1)), (114, 44.7))

    def test_the_ten_question_types_add_up_to_500_and_completeness_is_the_weakest(self):
        types = {name: row for name, row in self.rows.items() if name.startswith("type:")}
        self.assertEqual((len(types), sum(row["questions"] for row in types.values())), (10, 500))
        self.assertEqual(min(types, key=lambda name: types[name]["means"]["score"]), "type:completeness")

    def test_the_run_names_its_prompt_answerer_and_judge(self):
        self.assertEqual((self.config["prompt"], self.config["answerer"], self.config["judge"]),
                         ("ANSWER_PROMPT_V2", "gemma4:26b", "claude-haiku-4-5"))


@unittest.skipUnless((answer_metrics.RUNS_DIR / answer_metrics.DEEPSEEK_RUN / "metrics.json").is_file(), "no deepseek answer metrics yet")
class RealDeepSeekAnswers(unittest.TestCase):
    def test_deepseek_is_67_97_over_the_same_500_questions(self):
        saved = json.loads((answer_metrics.RUNS_DIR / answer_metrics.DEEPSEEK_RUN / "metrics.json").read_text())
        overall = saved["rows"][0]
        self.assertEqual((overall["group"], overall["questions"], round(overall["means"]["score"] * 100, 2)),
                         ("overall", 500, 67.97))
        self.assertEqual((saved["config"]["prompt"], saved["config"]["answerer"]), ("ANSWER_PROMPT_V2", "deepseek-v4-pro"))


@unittest.skipUnless((answer_metrics.RUNS_DIR / answer_metrics.V3_RUN / "metrics.json").is_file(), "no v3 answer metrics yet")
class RealV3Answers(unittest.TestCase):
    def test_prompt_v3_is_77_50_over_the_same_500_questions(self):  # GEN-13d: 3 answers are empty and count as wrong
        saved = json.loads((answer_metrics.RUNS_DIR / answer_metrics.V3_RUN / "metrics.json").read_text())
        overall = saved["rows"][0]
        self.assertEqual((overall["group"], overall["questions"], round(overall["means"]["score"] * 100, 2)),
                         ("overall", 500, 77.5))
        self.assertEqual((saved["config"]["prompt"], saved["config"]["answerer"]), ("ANSWER_PROMPT_V3", "deepseek-v4-pro"))


class EveryRun(unittest.TestCase):
    def test_the_runs_are_gemma_then_deepseek_then_prompt_v3_on_the_same_judge(self):
        self.assertEqual([(name, run.config["answerer"], run.config["prompt"], run.config["judge"])
                          for name, run in answer_metrics.ANSWER_RUNS.items()],
                         [("2026-10-04-answers-v4-gemma4-v2", "gemma4:26b", "ANSWER_PROMPT_V2", "claude-haiku-4-5"),
                          ("2026-10-04-answers-v4-deepseek-v4-pro-v2", "deepseek-v4-pro", "ANSWER_PROMPT_V2", "claude-haiku-4-5"),
                          ("2026-10-04-answers-v4-deepseek-v4-pro-v3", "deepseek-v4-pro", "ANSWER_PROMPT_V3", "claude-haiku-4-5")])

    def test_each_run_has_a_name_and_the_one_thing_it_changed(self):  # GEN-13d: two runs share an answerer
        self.assertEqual([(run.config["name"], run.config["change"]) for run in answer_metrics.ANSWER_RUNS.values()],
                         [("gemma4:26b · prompt v2", "Base: 10 whole documents from v4, prompt v2"),
                          ("deepseek-v4-pro · prompt v2", "Same documents and prompt, a stronger model"),
                          ("deepseek-v4-pro · prompt v3", "Same model and documents, prompt v3: quotes before the answer")])
        self.assertEqual(answer_metrics.RUN, answer_metrics.RUNS_DIR / "2026-10-04-answers-v4-gemma4-v2")


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(answer_metrics).failed, 0)
        self.assertEqual(METRICS, ("correct", "completeness", "score"))


if __name__ == "__main__":
    unittest.main()

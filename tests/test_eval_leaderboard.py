"""GEN-6: overall_score, the leaderboard's number from the official scorer's results.json.

Run: uv run python -m unittest tests.test_eval_leaderboard
"""
import doctest
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.eval import leaderboard  # noqa: E402
from pipeline.eval.leaderboard import overall_score  # noqa: E402

PUBLISHED = ROOT / "data/_leaderboard"


def results_of(*rows):
    return {"questions": [{"question_id": f"q{n}", "answer_correct": correct, "completeness_pct": complete}
                          for n, (correct, complete) in enumerate(rows)]}


class OverallScore(unittest.TestCase):
    def test_a_wrong_answer_scores_zero_however_complete(self):
        self.assertEqual(overall_score(results_of((False, 100.0))), 0.0)

    def test_a_correct_answer_scores_its_completeness(self):
        self.assertEqual(overall_score(results_of((True, 75.0))), 75.0)

    def test_the_mean_over_questions_rounded_as_the_leaderboard(self):
        self.assertEqual(overall_score(results_of((True, 100.0), (False, 100.0), (True, 33.333))), 44.44)


@unittest.skipUnless((PUBLISHED / "results_bm25.json").is_file() and (PUBLISHED / "results_mixedbread.json").is_file(),
                     "published results absent from data/_leaderboard")
class PublishedResults(unittest.TestCase):
    def test_bm25_gpt_5_4_and_mixedbread_score_as_on_the_leaderboard(self):
        scores = [overall_score(json.loads((PUBLISHED / name).read_text()))
                  for name in ("results_bm25.json", "results_mixedbread.json")]
        self.assertEqual(scores, [50.6, 86.58])


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(leaderboard).failed, 0)


if __name__ == "__main__":
    unittest.main()

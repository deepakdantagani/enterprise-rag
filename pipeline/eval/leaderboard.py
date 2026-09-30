"""GEN-6: overall_score, the leaderboard's number from the official scorer's results.json.

The leaderboard ranks systems by the mean over all 500 questions of answer_correct (0 or 1)
× completeness_pct, rounded to 2 places (its transform_raw_data.py). A wrong answer scores 0
however complete it is: on the published BM25 + GPT-5.4 results, qst_0001 is correct and 100%
complete (10 MiB per file, 50 MiB per request) and adds 100; the file averages 50.6, though
its mean completeness alone is 55.95.

    >>> overall_score({"questions": [{"answer_correct": True, "completeness_pct": 75.0},
    ...                              {"answer_correct": False, "completeness_pct": 100.0}]})
    37.5
"""


def overall_score(results: dict) -> float:
    """The leaderboard's overall score of one results.json (metrics_based_eval.py's output)."""
    scores = [(1 if row["answer_correct"] else 0) * row["completeness_pct"] for row in results["questions"]]
    return round(sum(scores) / len(scores), 2) if scores else 0.0

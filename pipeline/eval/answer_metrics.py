"""GEN-11a: answer_rows, the judged answers of one run as metrics.json rows, overall and per source.

The retrieval report is drawn from each run's metrics.json (EVAL-5a), a row per group with its
means; the judged answers were only a jsonl under data/, which is not committed. The same shape
puts them in the report: on the 500 v2 answers (ANSWER_PROMPT_V2, gemma4:26b, judged by
claude-haiku-4-5) the overall score is 62.43, but confluence (114 questions) scores 44.7 and
hubspot (34) 67.6. A question counts under every source of its expected documents, as in the
retrieval rows; the 30 questions with no expected document are the group "source:none". All
three means are fractions of 1: correct, completeness, and score (correct × completeness, the
leaderboard's number).

    >>> answer_rows([{"question_id": "q1", "source_types": ["slack"]}],
    ...             [{"question_id": "q1", "answer_correct": True, "completeness_pct": 75.0}])[1]
    {'group': 'source:slack', 'questions': 1, 'means': {'correct': 1.0, 'completeness': 0.75, 'score': 0.75}}

Run: uv run python -m pipeline.eval.answer_metrics
"""
import json
from pathlib import Path
from typing import Dict, List, Sequence

from pipeline.eval.rerank import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/_full/questions.jsonl"
JUDGMENTS = ROOT / "data/_index/judgments/v4-gemma4-v2__claude-haiku-4-5.jsonl"
RUN = ROOT / "docs/eval/runs/2026-10-04-answers-v4-gemma4-v2"  # the base answer run: retrieval v4, prompt v2
CONFIG = {"retrieval": "v4 (titles, voyage-4-lite + BM25, RRF, top 100 reranked by rerank-3-lite)",
          "documents_read": 10, "prompt": "ANSWER_PROMPT_V2", "answerer": "gemma4:26b",
          "judge": "claude-haiku-4-5", "note": "our judge, not the leaderboard's gpt-5.4"}
METRICS = ("correct", "completeness", "score")


def means_of(judgments: Sequence[dict]) -> Dict[str, float]:
    count = len(judgments)
    return {"correct": sum(row["answer_correct"] for row in judgments) / count,
            "completeness": sum(row["completeness_pct"] for row in judgments) / (100 * count),
            "score": sum(row["answer_correct"] * row["completeness_pct"] for row in judgments) / (100 * count)}


def answer_rows(questions: Sequence[dict], judgments: Sequence[dict]) -> List[dict]:
    """One row for all questions, then one per source in name order; every question must be judged."""
    judged = {row["question_id"]: row for row in judgments}
    groups: Dict[str, List[dict]] = {"overall": [judged[question["question_id"]] for question in questions]}
    for question in questions:
        for source in sorted(question["source_types"]) or ["none"]:
            groups.setdefault(f"source:{source}", []).append(judged[question["question_id"]])
    names = ["overall"] + sorted(name for name in groups if name != "overall")
    return [{"group": name, "questions": len(groups[name]), "means": means_of(groups[name])} for name in names]


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    rows = answer_rows(read_jsonl(QUESTIONS), read_jsonl(JUDGMENTS))
    (RUN / "metrics.json").write_text(json.dumps({"config": CONFIG, "rows": rows}, indent=1) + "\n")


if __name__ == "__main__":
    main()

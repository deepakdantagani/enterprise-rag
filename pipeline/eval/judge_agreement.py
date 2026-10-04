"""GEN-9f: does our judge (claude-haiku-4-5) agree with the leaderboard's (gpt-5.4)?

    uv run python -m pipeline.eval.judge_agreement    # needs OPENAI_API_KEY in .env; paid, resumable

Every score in docs/eval/results.md is from our judge. The leaderboard's judge is gpt-5.4, with
the same two prompts. Here 100 of our v3 answers, the same share of each question type as in the
500 (35 basic, 25 semantic, ...), are judged again on gpt-5.4 and compared verdict by verdict.

    >>> ours = [{"question_id": "q1", "answer_correct": True, "completeness_pct": 50.0,
    ...          "facts": [{"fact": "a", "contained": True}, {"fact": "b", "contained": False}]}]
    >>> theirs = [{"question_id": "q1", "answer_correct": True, "completeness_pct": 100.0,
    ...            "facts": [{"fact": "a", "contained": True}, {"fact": "b", "contained": True}]}]
    >>> found = agreement(ours, theirs)
    >>> found["correct_agreement"], found["fact_agreement"], found["score_ours"], found["score_theirs"]
    (1.0, 0.5, 50.0, 100.0)
"""
import asyncio
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Collection, List

from pipeline.eval.judge import ANSWERS, JUDGMENTS as OUR_JUDGMENTS, QUESTIONS, judge_answers
from pipeline.eval.leaderboard import overall_score
from pipeline.eval.rerank import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_JUDGE = "gpt-5.4"
SAMPLE = 100
SAMPLE_ANSWERS = ROOT / "data/_index/answers/agreement-100__v4-deepseek-v4-pro-v3.jsonl"  # the 100 answers, written here
GPT_JUDGMENTS = ROOT / "data/_index/judgments/agreement-100__v4-deepseek-v4-pro-v3__gpt-5.4.jsonl"  # written here


def sample_ids(questions: List[dict], count: int = SAMPLE, seed: int = 0, skip: Collection[str] = ()) -> List[str]:
    """count question ids, each question type keeping its share, picked by a seeded shuffle; skip is never picked."""
    by_type = defaultdict(list)
    for question in questions:
        by_type[question["question_type"]].append(question["question_id"])
    picked = []
    for question_type in sorted(by_type):
        ids = sorted(by_type[question_type])
        share = round(len(ids) * count / len(questions))
        picked += random.Random(f"{seed}:{question_type}").sample([qid for qid in ids if qid not in skip], share)
    return sorted(picked)


def agreement(ours: List[dict], theirs: List[dict]) -> dict:
    """How two judges agree on the questions both judged: correctness, each fact, and both overall scores."""
    theirs_by_id = {row["question_id"]: row for row in theirs}
    pairs = [(row, theirs_by_id[row["question_id"]]) for row in ours if row["question_id"] in theirs_by_id]
    facts = [mine["contained"] == other["contained"]
             for a, b in pairs for mine, other in zip(a["facts"], b["facts"])]
    return {
        "questions": len(pairs),
        "correct_agreement": round(sum(a["answer_correct"] == b["answer_correct"] for a, b in pairs) / len(pairs), 4),
        "fact_agreement": round(sum(facts) / len(facts), 4),
        "score_ours": overall_score({"questions": [a for a, _ in pairs]}),
        "score_theirs": overall_score({"questions": [b for _, b in pairs]}),
        "disagreements": [{"question_id": a["question_id"], "ours": a["answer_correct"], "theirs": b["answer_correct"]}
                          for a, b in pairs if a["answer_correct"] != b["answer_correct"]],
    }


async def main() -> None:
    # The 100 answers: a seeded sample, never an empty answer (the judge cannot judge one)
    answers = {row["question_id"]: row for row in read_jsonl(ANSWERS)}
    empty = {question_id for question_id, row in answers.items() if not row["answer"]}
    sample = sample_ids(read_jsonl(QUESTIONS), skip=empty)
    SAMPLE_ANSWERS.write_text("".join(json.dumps(answers[question_id]) + "\n" for question_id in sample))

    # Judge them on gpt-5.4, then compare with our judge's verdicts on the same answers
    await judge_answers(SAMPLE_ANSWERS, GPT_JUDGMENTS, OFFICIAL_JUDGE)
    print(json.dumps(agreement(read_jsonl(OUR_JUDGMENTS), read_jsonl(GPT_JUDGMENTS)), indent=2))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    asyncio.run(main())

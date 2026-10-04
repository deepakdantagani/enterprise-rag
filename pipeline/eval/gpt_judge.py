"""GEN-9g: every prompt v3 answer judged on gpt-5.4, the leaderboard's judge model.

    uv run python -m pipeline.eval.gpt_judge    # needs OPENAI_API_KEY in .env; paid, resumable

GEN-9f judged 100 answers on gpt-5.4 and found our judge within 4 verdicts of it. This judges
the other answers too, starting from those 100 so none is paid for twice. It is our judge code
(the benchmark's two prompts, structured replies) on the leaderboard's model, not the
benchmark's own scorer script, so the number is close to a leaderboard score, not one.

An empty answer cannot be judged (qst_0351, qst_0358, qst_0362: the quotes used the whole
output). It is recorded as wrong:

    >>> not_judged({"question_id": "qst_0351", "answer_facts": ["Pause the rollout."]})["facts"]
    [{'fact': 'Pause the rollout.', 'contained': False}]
"""
import asyncio
import json
import shutil
from pathlib import Path

from pipeline.eval.judge import ANSWERS, JUDGMENTS as OUR_JUDGMENTS, QUESTIONS, judge_answers
from pipeline.eval.judge_agreement import GPT_JUDGMENTS, OFFICIAL_JUDGE, agreement
from pipeline.eval.rerank import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
JUDGEABLE = ROOT / "data/_index/answers/v4-deepseek-v4-pro-v3__not-empty.jsonl"  # written here
GPT_ALL = ROOT / "data/_index/judgments/v4-deepseek-v4-pro-v3__gpt-5.4.jsonl"  # written here


def not_judged(question: dict) -> dict:
    """The row of an empty answer: wrong, 0% complete, every fact not contained."""
    return {"question_id": question["question_id"], "answer_correct": False, "completeness_pct": 0.0,
            "reason": "Not judged: the answer is empty.",
            "facts": [{"fact": fact, "contained": False} for fact in question["answer_facts"]]}


async def main() -> None:
    # The answers a judge can read: every answer that is not empty
    answers = read_jsonl(ANSWERS)
    JUDGEABLE.write_text("".join(json.dumps(row) + "\n" for row in answers if row["answer"]))

    # Start from the 100 judged in GEN-9f, then judge the rest
    if not GPT_ALL.exists():
        shutil.copy(GPT_JUDGMENTS, GPT_ALL)
    await judge_answers(JUDGEABLE, GPT_ALL, OFFICIAL_JUDGE)

    # The empty answers count as wrong
    judged = {row["question_id"] for row in read_jsonl(GPT_ALL)}
    questions = {row["question_id"]: row for row in read_jsonl(QUESTIONS)}
    with GPT_ALL.open("a") as out:
        for row in answers:
            if row["question_id"] not in judged:
                out.write(json.dumps(not_judged(questions[row["question_id"]])) + "\n")

    found = agreement(read_jsonl(OUR_JUDGMENTS), read_jsonl(GPT_ALL))
    print(json.dumps({**found, "disagreements": len(found["disagreements"])}, indent=2))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    asyncio.run(main())

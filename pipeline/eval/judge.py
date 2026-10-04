"""GEN-9a to GEN-9d: judge our saved answers, read top to bottom: correctness x completeness = the leaderboard's score.

    uv run python -m pipeline.eval.judge        # needs ANTHROPIC_API_KEY in .env; resumable

The leaderboard scores an answer as correct (0 or 1) x completeness (%). For qst_0009 the judge
makes 6 calls:

    1 correctness call   question + gold answer + our answer   -> aligned: yes / no
    5 completeness calls our answer + one fact each            -> contained: true / false

Correctness is LlamaIndex's CorrectnessEvaluator with the benchmark's prompt; its 1-to-5 scale
is used at its two ends only (yes 5.0, no 1.0, passing at 4.0). Completeness is the one
evaluator we write, because LlamaIndex has none that checks one statement at a time; its reply
is Claude's structured output (astructured_predict sends FactVerdict as the output schema), so
no parser is needed. LlamaIndex's BatchEvalRunner runs both over 25 answers per call, and each
batch is saved as soon as it is judged, so a crash or a re-run never pays twice. The prompts
are in judge_prompts.py; examples/judge_one_question.py is the same call for one question.

    >>> aligned('{"reason": "Same package terms.", "aligned": "yes"}')
    (5.0, 'Same package terms.')
    >>> FactCheck(answer="Redwood proposed a 12-month commit package.", facts=["A 99.9 percent latency SLO."]).facts
    ['A 99.9 percent latency SLO.']
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Annotated, Any, List, Optional, Sequence, Tuple

from llama_index.core.evaluation import BaseEvaluator, BatchEvalRunner, CorrectnessEvaluator, EvaluationResult
from llama_index.core.llms import LLM
from llama_index.llms.anthropic import Anthropic
from pydantic import BaseModel, Field

from pipeline.eval.judge_prompts import CORRECTNESS_TEMPLATE, FACT_TEMPLATE
from pipeline.eval.leaderboard import overall_score
from pipeline.eval.rerank import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/_full/questions.jsonl"  # the benchmark: question, gold_answer, answer_facts
ANSWERS = ROOT / "data/_index/answers/v4-gemma4-base.jsonl"  # ours: the 500 saved answers (GEN-5)
JUDGMENTS = ROOT / "data/_index/judgments/v4-gemma4-base__claude-haiku-4-5.jsonl"  # written here
BATCH = 25  # answers judged per call, then saved


# 1. Reads the correctness judge's reply

ALIGNED, MISALIGNED = 5.0, 1.0  # CorrectnessEvaluator passes a score of 4.0 or more


def aligned(reply: str) -> Tuple[float, str]:
    """The judge's {"reason", "aligned": "yes"|"no"} reply as CorrectnessEvaluator's (score, reason)."""
    found = re.search(r"\{.*\}", reply, re.DOTALL)  # the JSON may sit inside a code fence
    if not found:
        raise ValueError(f"no JSON verdict in the judge's reply: {reply!r}")
    verdict = json.loads(found.group())
    is_aligned = re.search(r"\byes\b", verdict["aligned"], re.IGNORECASE) is not None  # as the official scorer reads it
    return (ALIGNED if is_aligned else MISALIGNED), verdict["reason"]


# 2. The completeness judge: one structured call per fact

class FactCheck(BaseModel):
    """Input: what one completeness judgment needs, validated before any call is paid for."""
    answer: str = Field(min_length=1)
    facts: List[Annotated[str, Field(min_length=1)]] = Field(min_length=1)


class FactVerdict(BaseModel):
    """Output: the judge's structured reply for one fact."""
    contained: bool = Field(description="True if the answer is consistent with and contains the statement.")


JUDGE_KWARGS = {"temperature": 0}  # LlamaIndex's Anthropic structured call takes sampling settings only this way


class CompletenessEvaluator(BaseEvaluator):
    """The share of a question's facts that the answer contains."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def _get_prompts(self) -> dict:
        return {"fact_template": FACT_TEMPLATE}

    def _update_prompts(self, prompts: dict) -> None:
        pass  # the benchmark's prompt is fixed

    async def aevaluate(self, query: Optional[str] = None, response: Optional[str] = None,
                        contexts: Optional[Sequence[str]] = None, facts: Sequence[str] = (),
                        **kwargs: Any) -> EvaluationResult:
        check = FactCheck(answer=response or "", facts=list(facts))  # an empty answer or no facts: no call is made
        contained = []
        for fact in check.facts:
            verdict = await self._llm.astructured_predict(FactVerdict, FACT_TEMPLATE, llm_kwargs=JUDGE_KWARGS,
                                                          answer=check.answer, statement=fact)
            contained.append(verdict.contained)
        share = sum(contained) / len(contained)
        return EvaluationResult(query=query, response=response, score=share, passing=share == 1.0,
                                feedback=json.dumps([{"fact": fact, "contained": found}
                                                     for fact, found in zip(check.facts, contained)]))


# 3. The run

async def main() -> None:
    # Load the benchmark's questions and our answers; skip the answers already judged
    questions = {row["question_id"]: row for row in read_jsonl(QUESTIONS)}
    judged = {row["question_id"] for row in read_jsonl(JUDGMENTS)} if JUDGMENTS.exists() else set()
    answers = [row for row in read_jsonl(ANSWERS) if row["question_id"] not in judged]
    JUDGMENTS.parent.mkdir(parents=True, exist_ok=True)

    # Judge 25 answers per call and save after each call, so a crash loses at most 25
    for start in range(0, len(answers), BATCH):
        batch = answers[start:start + BATCH]

        # The inputs for this batch, one entry per answer
        asked, ours, golds, facts = [], [], [], []
        for answer in batch:
            question = questions[answer["question_id"]]
            asked.append(question["question"])
            ours.append(answer["answer"])
            golds.append(question["gold_answer"])
            facts.append(question["answer_facts"])

        results = await BatchEvalRunner(
            # Who judges: two evaluators on Claude Haiku 4.5
            evaluators={
                "correctness": CorrectnessEvaluator(
                    llm=Anthropic(model="claude-haiku-4-5", temperature=0, max_tokens=256),
                    eval_template=CORRECTNESS_TEMPLATE, parser_function=aligned),
                "completeness": CompletenessEvaluator(Anthropic(model="claude-haiku-4-5")),
            },
            workers=8,  # questions judged at the same time
        ).aevaluate_response_strs(
            queries=asked,
            response_strs=ours,
            correctness={"reference": golds},  # only the correctness judge gets the gold answers
            completeness={"facts": facts},     # only the completeness judge gets the facts
        )

        # One saved line per question, in the official scorer's format
        with JUDGMENTS.open("a") as out:
            for answer, correct, complete in zip(batch, results["correctness"], results["completeness"]):
                out.write(json.dumps({"question_id": answer["question_id"], "answer_correct": correct.passing,
                                      "completeness_pct": round(complete.score * 100, 2), "reason": correct.feedback,
                                      "facts": json.loads(complete.feedback)}) + "\n")

    print("overall score:", overall_score({"questions": read_jsonl(JUDGMENTS)}))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    asyncio.run(main())

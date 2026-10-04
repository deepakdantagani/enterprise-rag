"""GEN-9a to GEN-9d: judge our saved answers, read top to bottom: correctness x completeness = the leaderboard's score.

    uv run python -m pipeline.eval.judge        # needs ANTHROPIC_API_KEY in .env; resumable

The leaderboard scores an answer as correct (0 or 1) x completeness (%). For qst_0009 the judge
makes 6 calls:

    1 correctness call   question + gold answer + our answer   -> {"reason": "...", "aligned": true | false}
    5 completeness calls our answer + one fact each            -> {"contained": true | false}

Both judges work the same way. The input is a Pydantic model checked before any call is paid
for (CorrectnessCheck, FactCheck). The prompt is the benchmark's own (judge_prompts.py). The
output is Claude's structured output: LlamaIndex's astructured_predict sends a Pydantic model as
the output schema (CorrectnessVerdict, FactVerdict), so the reply can only have that shape and
no parser is written. LlamaIndex's own CorrectnessEvaluator makes plain-text calls only, so both
evaluators are ours, on its BaseEvaluator interface. BatchEvalRunner runs them over 25 answers
per call, and each batch is saved as soon as it is judged, so a crash or a re-run never pays
twice. examples/judge_one_question.py is the same call for one question.

    >>> CorrectnessVerdict(reason="Same package terms.", aligned=True).aligned
    True
    >>> FactCheck(answer="Redwood proposed a 12-month commit package.", facts=["A 99.9 percent latency SLO."]).facts
    ['A 99.9 percent latency SLO.']
"""
import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, List, Optional, Sequence

from llama_index.core.evaluation import BaseEvaluator, BatchEvalRunner, EvaluationResult
from llama_index.core.llms import LLM
from llama_index.llms.anthropic import Anthropic
from pydantic import BaseModel, Field

from pipeline.eval.judge_prompts import CORRECTNESS_TEMPLATE, FACT_TEMPLATE
from pipeline.eval.leaderboard import overall_score
from pipeline.eval.rerank import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/_full/questions.jsonl"  # the benchmark: question, gold_answer, answer_facts
ANSWERS = ROOT / "data/_index/answers/v4-deepseek-v4-pro-v2.jsonl"  # ours: deepseek-v4-pro on ANSWER_PROMPT_V2 (gemma: v4-gemma4-v2)
JUDGMENTS = ROOT / "data/_index/judgments/v4-deepseek-v4-pro-v2__claude-haiku-4-5.jsonl"  # written here
BATCH = 25  # answers judged per call, then saved


# Temperature 0, so a re-run gives the same verdicts. The Anthropic SDK 1.x has no temperature
# parameter, so it goes in the request body; claude-haiku-4-5 accepts it (Opus 5.5 and Sonnet 5.5 would not).
JUDGE_KWARGS = {"extra_body": {"temperature": 0}}


# 1. The correctness judge: one structured call per answer

class CorrectnessCheck(BaseModel):
    """Input: what one correctness judgment needs, validated before the call is paid for."""
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    gold_answer: str = Field(min_length=1)


class CorrectnessVerdict(BaseModel):
    """Output: the judge's structured reply for one answer."""
    reason: str = Field(description="One sentence on why the candidate answer is aligned or misaligned.")
    aligned: bool = Field(description="True if the candidate answer is aligned with the gold answer (yes), else false.")


class StructuredCorrectnessEvaluator(BaseEvaluator):
    """Does our answer agree with the gold answer? LlamaIndex's CorrectnessEvaluator, with a structured reply."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def _get_prompts(self) -> dict:
        return {"eval_template": CORRECTNESS_TEMPLATE}

    def _update_prompts(self, prompts: dict) -> None:
        pass  # the benchmark's prompt is fixed

    async def aevaluate(self, query: Optional[str] = None, response: Optional[str] = None,
                        contexts: Optional[Sequence[str]] = None, reference: Optional[str] = None,
                        **kwargs: Any) -> EvaluationResult:
        check = CorrectnessCheck(question=query or "", answer=response or "", gold_answer=reference or "")
        verdict = await self._llm.astructured_predict(CorrectnessVerdict, CORRECTNESS_TEMPLATE, llm_kwargs=JUDGE_KWARGS,
                                                      query=check.question, reference_answer=check.gold_answer,
                                                      generated_answer=check.answer)
        return EvaluationResult(query=query, response=response, passing=verdict.aligned,
                                score=1.0 if verdict.aligned else 0.0, feedback=verdict.reason)


# 2. The completeness judge: one structured call per fact

class FactCheck(BaseModel):
    """Input: what one completeness judgment needs, validated before any call is paid for."""
    answer: str = Field(min_length=1)
    facts: List[Annotated[str, Field(min_length=1)]] = Field(min_length=1)


class FactVerdict(BaseModel):
    """Output: the judge's structured reply for one fact."""
    contained: bool = Field(description="True if the answer is consistent with and contains the statement.")


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
                "correctness": StructuredCorrectnessEvaluator(Anthropic(model="claude-haiku-4-5")),
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

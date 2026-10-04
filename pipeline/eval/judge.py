"""GEN-9a, GEN-9b, GEN-9c: the judge, read top to bottom: correctness, completeness, then the model and the runner.

The leaderboard scores an answer as correct (0 or 1) x completeness (%). For qst_0009 the judge
makes 6 calls:

    1 correctness call   question + gold answer + our answer   -> aligned: yes / no
    5 completeness calls our answer + one fact each            -> contained: true / false

Correctness is LlamaIndex's CorrectnessEvaluator with the benchmark's prompt; its 1-to-5 scale
is used at its two ends only (yes 5.0, no 1.0, passing at 4.0). Completeness is the one
evaluator we write, because LlamaIndex has none that checks one statement at a time; its reply
is Claude's structured output (astructured_predict sends FactVerdict as the output schema), so
no parser is needed. The prompts are in judge_prompts.py. LlamaIndex's BatchEvalRunner runs both
evaluators over many questions, 8 at a time (GEN-9c); examples/judge_one_question.py shows the
whole thing as one flat script.

    >>> aligned('{"reason": "Same package terms.", "aligned": "yes"}')
    (5.0, 'Same package terms.')
    >>> FactCheck(answer="Redwood proposed a 12-month commit package.", facts=["A 99.9 percent latency SLO."]).facts
    ['A 99.9 percent latency SLO.']
"""
import json
import re
from typing import Annotated, Any, List, Optional, Sequence, Tuple

from llama_index.core.evaluation import BaseEvaluator, BatchEvalRunner, CorrectnessEvaluator, EvaluationResult
from llama_index.core.llms import LLM
from pydantic import BaseModel, Field

from pipeline.eval.judge_prompts import CORRECTNESS_TEMPLATE, FACT_TEMPLATE

# 1. Correctness: LlamaIndex's evaluator + the benchmark's prompt + a reader for its reply

ALIGNED, MISALIGNED = 5.0, 1.0  # CorrectnessEvaluator passes a score of 4.0 or more


def aligned(reply: str) -> Tuple[float, str]:
    """The judge's {"reason", "aligned": "yes"|"no"} reply as CorrectnessEvaluator's (score, reason)."""
    found = re.search(r"\{.*\}", reply, re.DOTALL)  # the JSON may sit inside a code fence
    if not found:
        raise ValueError(f"no JSON verdict in the judge's reply: {reply!r}")
    verdict = json.loads(found.group())
    is_aligned = re.search(r"\byes\b", verdict["aligned"], re.IGNORECASE) is not None  # as the official scorer reads it
    return (ALIGNED if is_aligned else MISALIGNED), verdict["reason"]


def correctness_judge(llm: LLM) -> CorrectnessEvaluator:
    return CorrectnessEvaluator(llm=llm, eval_template=CORRECTNESS_TEMPLATE, parser_function=aligned)


# 2. Completeness: one structured call per fact

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


# 3. The judge model and the runner

JUDGE = "claude-haiku-4-5"  # about $2 to $3 for the 500 answers; the official judge is gpt-5.4 (GEN-9f compares)
MAX_REPLY_TOKENS = 256  # caps the reply only: a correctness reply is about 50 tokens
QUESTIONS_AT_ONCE = 8


def judge_llm(model: str = JUDGE, api_key: Optional[str] = None) -> LLM:
    from llama_index.llms.anthropic import Anthropic
    return Anthropic(model=model, temperature=0, max_tokens=MAX_REPLY_TOKENS, api_key=api_key)


def judge_runner(llm: LLM, workers: int = QUESTIONS_AT_ONCE) -> BatchEvalRunner:
    """Both judges over many questions: pass correctness={"reference": golds} and completeness={"facts": facts}."""
    return BatchEvalRunner({"correctness": correctness_judge(llm), "completeness": CompletenessEvaluator(llm)},
                           workers=workers)

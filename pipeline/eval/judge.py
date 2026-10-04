"""GEN-9a: aligned and correctness_judge, the benchmark's correctness prompt on LlamaIndex's CorrectnessEvaluator.

The leaderboard's judge asks one question per answer: does the candidate agree with the gold
answer (ANSWER_WHOLISTIC_EVALUATION_PROMPT, EnterpriseRAG-Bench src/prompts/answer_evaluation.py,
MIT)? For qst_0009 it reads the query, the gold answer ("Redwood said it wouldn't match the
competitor's 50% blanket Year-1 discount … 12-month committed prepay package …") and ours
("Redwood proposed a 12-month commit package …") and replies {"reason", "aligned"}.
CorrectnessEvaluator already makes that call and returns an EvaluationResult; it only needs the
benchmark's wording as its template and a parser for the reply. Correctness is yes or no: the
evaluator's 1-to-5 scale is used at its two ends only, and partial credit comes from
completeness (GEN-9b).

    >>> aligned('{"reason": "Same package terms.", "aligned": "yes"}')
    (5.0, 'Same package terms.')

GEN-9b: fact_verdict and CompletenessEvaluator. Completeness is the share of a question's
answer_facts that the answer contains. The judge reads our answer and one fact per call
(INDIVIDUAL_FACT_VALIDATOR_PROMPT; never the question or the gold answer) and replies yes or no,
read from the first line as the official scorer does (validate_single_fact). qst_0009 has 5
facts, so 5 calls; 4 contained is 0.8. LlamaIndex has no evaluator that checks one statement at
a time, so this is the one evaluator we write.

    >>> fact_verdict("The package included a 99.9 percent latency SLO.", "yes")
    FactVerdict(fact='The package included a 99.9 percent latency SLO.', contained=True)
"""
import asyncio
import json
import re
from typing import Any, Optional, Sequence, Tuple

from llama_index.core import PromptTemplate
from llama_index.core.evaluation import BaseEvaluator, CorrectnessEvaluator, EvaluationResult
from llama_index.core.llms import LLM
from pydantic import BaseModel

ALIGNED, MISALIGNED = 5.0, 1.0  # CorrectnessEvaluator passes a score of 4.0 or more

# The benchmark's text, word for word (tests/fixtures/benchmark); only gold_answer and
# candidate_answer are renamed to the names CorrectnessEvaluator fills.
CORRECTNESS_TEMPLATE = PromptTemplate(
    "You are a wholistic and detail-oriented answer evaluator. Given a query, a gold answer, and a "
    "candidate answer, evaluate if the candidate answer aligned with the gold answer.\n"
    "Use the following metrics for evaluating the answer:\n"
    "- The candidate answer must provide loosely the same information as the gold answer. The core "
    "aspects directly asked by the query must be addressed in the candidate answer and they must not "
    "conflict with the gold answer.\n"
    "- If there are any specific quantities mentioned in both answers, they must match.\n"
    "- The candidate answer is not required to contain all of the same details as the gold answer.\n"
    "- The candidate answer must address the key parts of the query, if it is missing anything critical "
    "to the question, it is misaligned.\n"
    "- The candidate answer may contain more details, richer information, or other helpful relevant "
    "information than the gold answer, this is ok.\n"
    "- The candidate answer may offer up additional loosely related information that adds to the context "
    "of the answer, this is ok as long as it does not lead the user to an incorrect conclusion (compared "
    "to the gold answer).\n"
    "- Do not penalize the candidate answer for stylistic differences. If the candidate answer offers "
    "follow up questions, asks additional clarifications to the user, or offers additional context, this "
    "is ok as long as it contains the necessary information to answer the question.\n"
    "\n"
    "There is a separate check for answer completeness, this is not in scope for this evaluation. "
    "However, if there are core parts of the question being left out, this is misaligned.\n"
    "\n"
    "## Query\n"
    "```\n"
    "{query}\n"
    "```\n"
    "\n"
    "## Gold Answer\n"
    "```\n"
    "{reference_answer}\n"
    "```\n"
    "\n"
    "## Candidate Answer\n"
    "```\n"
    "{generated_answer}\n"
    "```\n"
    "\n"
    "## Output Format\n"
    "Output a JSON with \"reason\" and \"aligned\" fields. The \"reason\" field should be a as concise as "
    "possible (max 1 sentence) explanation of why the candidate answer is aligned or misaligned with the "
    "gold answer. The \"aligned\" field should be a simple \"yes\" or \"no\", use only those two strings "
    "literally and nothing else.\n"
    "\n"
    "CRITICAL: Output only a JSON object with the following fields in the order shown below (with no "
    "additional text or formatting):\n"
    "{{\n"
    "  \"reason\": \"reason for the classification\",\n"
    "  \"aligned\": \"yes or no\"\n"
    "}}")


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


FACT_TEMPLATE = PromptTemplate(  # the benchmark's INDIVIDUAL_FACT_VALIDATOR_PROMPT, unchanged
    "You are an answer validator. Given an answer and a statement, determine if the answer is consistent "
    "with and contains the information in the statement. The answer may contain more details or richer "
    "information than the statement but as long as it does not contradict the statement, this is valid. "
    "If there are negative statements such as \"The answer must not say...\", it is valid if the answer "
    "mentions the statement with caveats or qualifications. It is valid if additional context is shared "
    "for completeness however hallucinations are not allowed. Output a simple yes or no for if the "
    "answer is consistent with and contains the information in the statement.\n"
    "\n"
    "## Answer\n"
    "```\n"
    "{answer}\n"
    "```\n"
    "\n"
    "## Statement\n"
    "```\n"
    "{statement}\n"
    "```\n"
    "\n"
    "CRITICAL: output only a simple yes if the answer is consistent with the statement or a no if the "
    "answer does not contain the information in the statement or contradicts the statement.")


class FactVerdict(BaseModel):
    fact: str
    contained: bool


def fact_verdict(fact: str, reply: str) -> FactVerdict:
    """The judge's yes or no on one fact, read from the reply's first line as the official scorer reads it."""
    first_line = reply.strip().splitlines()[0] if reply.strip() else ""
    if not re.search(r"\b(yes|no)\b", first_line, re.IGNORECASE):
        raise ValueError(f"neither yes nor no in the judge's reply: {reply!r}")
    return FactVerdict(fact=fact, contained=re.search(r"\byes\b", first_line, re.IGNORECASE) is not None)


class CompletenessEvaluator(BaseEvaluator):
    """The share of a question's facts that the answer contains, one judge call per fact."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def _get_prompts(self) -> dict:
        return {"fact_template": FACT_TEMPLATE}

    def _update_prompts(self, prompts: dict) -> None:
        pass  # the benchmark's prompt is fixed

    async def aevaluate(self, query: Optional[str] = None, response: Optional[str] = None,
                        contexts: Optional[Sequence[str]] = None, facts: Sequence[str] = (),
                        **kwargs: Any) -> EvaluationResult:
        if not facts:
            raise ValueError("completeness needs the question's answer_facts")
        replies = await asyncio.gather(*(self._llm.apredict(FACT_TEMPLATE, answer=response, statement=fact)
                                         for fact in facts))
        verdicts = [fact_verdict(fact, reply) for fact, reply in zip(facts, replies)]
        share = sum(verdict.contained for verdict in verdicts) / len(verdicts)
        return EvaluationResult(query=query, response=response, score=share, passing=share == 1.0,
                                feedback=json.dumps([verdict.model_dump() for verdict in verdicts]))

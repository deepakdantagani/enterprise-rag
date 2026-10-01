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
"""
import json
import re
from typing import Tuple

from llama_index.core import PromptTemplate
from llama_index.core.evaluation import CorrectnessEvaluator
from llama_index.core.llms import LLM

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

"""GEN-9a, GEN-9b: the judge's two prompts, the benchmark's own text.

Copied from EnterpriseRAG-Bench src/prompts/answer_evaluation.py (MIT; pinned in
tests/fixtures/benchmark, commit 82954993d1), so our judge asks what the leaderboard's judge
asks. They live apart from judge.py so that file shows only its logic.

    >>> sorted(FACT_TEMPLATE.template_vars)
    ['answer', 'statement']
"""
from llama_index.core import PromptTemplate

# ANSWER_WHOLISTIC_EVALUATION_PROMPT, word for word; only gold_answer and candidate_answer are
# renamed to the names LlamaIndex's CorrectnessEvaluator fills.
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

# INDIVIDUAL_FACT_VALIDATOR_PROMPT, unchanged.
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

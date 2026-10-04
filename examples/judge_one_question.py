"""Judge one real answer (qst_0009), top to bottom: 1 correctness call and 5 completeness calls on Claude.

    uv run python examples/judge_one_question.py      # needs ANTHROPIC_API_KEY in .env; costs a fraction of a cent
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llama_index.core.evaluation import BatchEvalRunner  # noqa: E402

from pipeline.eval.judge import CompletenessEvaluator, correctness_judge, judge_llm  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# 1. The data: one benchmark question, the benchmark's gold answer and facts, and our saved answer
question = ("In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
            "instead of matching the competitor's 50 percent first-year discount and migration credit?")
gold_answer = ("Redwood said it wouldn't match the competitor's 50% blanket Year-1 discount and $60k migration credit, "
               "and instead proposed a 12-month committed prepay package with ~40% off list on prepay buckets plus a "
               "$50,000 one-time onboarding/migration credit tied to milestones, with an optional seat/license fee to "
               "cap variable spend and a 99.9% latency SLO for hosted US instances.")
facts = ["Redwood did not match the competitors 50 percent blanket Year 1 discount and 60k migration credit.",
         "Redwood proposed a 12 month committed prepay package with about 40 percent off list prices on prepay buckets.",
         "Redwood proposed a 50,000 one time onboarding or migration credit tied to milestones.",
         "The package included an optional seat or license fee to cap variable spend.",
         "The package included a 99.9 percent latency SLO for hosted US instances."]
our_answer = """Redwood proposed a 12-month commit package with the following components:
- Effective Year 1 discount: ~40% off list on committed prepay buckets (applies to token spend covered by the bucket).
- Onboarding allowance: $50,000 one-time credit tied to migration milestones (applies as invoice credit).
- Seat/license option: An option to add a predictable monthly seat fee to cap variable spend, where seat fees reduce effective unit cost further for covered traffic.
- Operational concession: 99.9% latency SLO for hosted instances in the US region, including a short remediation runbook in the SOW."""

# 2. The judge model
llm = judge_llm()  # Claude Haiku 4.5, temperature 0


# 3. Run both judges in one call and print the score
async def main():
    results = await BatchEvalRunner(
        evaluators={
            "correctness": correctness_judge(llm),       # does our answer agree with the gold answer?
            "completeness": CompletenessEvaluator(llm),  # how many of the facts does our answer contain?
        },
        workers=8,                                       # questions judged at the same time
    ).aevaluate_response_strs(
        queries=[question],
        response_strs=[our_answer],
        correctness={"reference": [gold_answer]},        # only the correctness judge gets the gold answer
        completeness={"facts": [facts]},                 # only the completeness judge gets the facts
    )
    correctness, completeness = results["correctness"][0], results["completeness"][0]
    print("correct:     ", correctness.passing, "|", correctness.feedback)
    print("completeness:", f"{completeness.score:.0%}", "|", completeness.feedback)
    print("score:       ", completeness.score * 100 if correctness.passing else 0.0)


asyncio.run(main())

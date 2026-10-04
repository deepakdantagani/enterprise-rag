"""Judge one real answer (qst_0009) in one call: 1 correctness call and 5 completeness calls on Claude.

    uv run python examples/judge_one_question.py      # needs ANTHROPIC_API_KEY in .env; costs a fraction of a cent
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from llama_index.core.evaluation import BatchEvalRunner
from llama_index.llms.anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.eval.judge import CompletenessEvaluator, StructuredCorrectnessEvaluator  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main():
    results = await BatchEvalRunner(
        # Who judges: two evaluators on Claude Haiku 4.5
        evaluators={
            # Does our answer agree with the gold answer?
            "correctness": StructuredCorrectnessEvaluator(Anthropic(model="claude-haiku-4-5", temperature=0)),
            # How many of the facts does our answer contain?
            "completeness": CompletenessEvaluator(Anthropic(model="claude-haiku-4-5", temperature=0)),
        },
        workers=8,  # questions judged at the same time
    ).aevaluate_response_strs(
        # The benchmark's question
        queries=[
            "In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
            "instead of matching the competitor's 50 percent first-year discount and migration credit?",
        ],
        # Our saved answer (gemma4:26b over v4's top 10 documents)
        response_strs=[
            "Redwood proposed a 12-month commit package with the following components:\n"
            "- Effective Year 1 discount: ~40% off list on committed prepay buckets (applies to token spend "
            "covered by the bucket).\n"
            "- Onboarding allowance: $50,000 one-time credit tied to migration milestones (applies as invoice "
            "credit).\n"
            "- Seat/license option: An option to add a predictable monthly seat fee to cap variable spend, where "
            "seat fees reduce effective unit cost further for covered traffic.\n"
            "- Operational concession: 99.9% latency SLO for hosted instances in the US region, including a short "
            "remediation runbook in the SOW.",
        ],
        # Only the correctness judge gets the benchmark's gold answer
        correctness={"reference": [
            "Redwood said it wouldn't match the competitor's 50% blanket Year-1 discount and $60k migration credit, "
            "and instead proposed a 12-month committed prepay package with ~40% off list on prepay buckets plus a "
            "$50,000 one-time onboarding/migration credit tied to milestones, with an optional seat/license fee to "
            "cap variable spend and a 99.9% latency SLO for hosted US instances.",
        ]},
        # Only the completeness judge gets the benchmark's facts, one call per fact
        completeness={"facts": [[
            "Redwood did not match the competitors 50 percent blanket Year 1 discount and 60k migration credit.",
            "Redwood proposed a 12 month committed prepay package with about 40 percent off list prices on prepay buckets.",
            "Redwood proposed a 50,000 one time onboarding or migration credit tied to milestones.",
            "The package included an optional seat or license fee to cap variable spend.",
            "The package included a 99.9 percent latency SLO for hosted US instances.",
        ]]},
    )

    # One result per judge for the one question
    print("correct:     ", results["correctness"][0].passing, "|", results["correctness"][0].feedback)
    print("completeness:", results["completeness"][0].score, "|", results["completeness"][0].feedback)


asyncio.run(main())

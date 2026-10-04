import asyncio
import contextlib
import doctest
import io
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata  # noqa: E402

from pipeline.eval import judge, judge_prompts  # noqa: E402
from pipeline.eval.judge import (CompletenessEvaluator, CorrectnessCheck, CorrectnessVerdict, FactCheck, FactVerdict,  # noqa: E402
                                 StructuredCorrectnessEvaluator)
from pipeline.eval.judge_prompts import CORRECTNESS_TEMPLATE, FACT_TEMPLATE  # noqa: E402

BENCHMARK_PROMPTS = ROOT / "tests/fixtures/benchmark/answer_evaluation.py"  # the judge's prompt file, unchanged

# qst_0009
QUERY = ("In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
         "instead of matching the competitor's 50 percent first-year discount and migration credit?")
GOLD = "Redwood said it wouldn't match the competitor's 50% blanket Year-1 discount and $60k migration credit"
OURS = "Redwood proposed a 12-month commit package with the following components:"
FACTS = ["Redwood did not match the competitors 50 percent blanket Year 1 discount and 60k migration credit.",
         "Redwood proposed a 12 month committed prepay package with about 40 percent off list prices on prepay buckets.",
         "Redwood proposed a 50,000 one time onboarding or migration credit tied to milestones.",
         "The package included an optional seat or license fee to cap variable spend.",
         "The package included a 99.9 percent latency SLO for hosted US instances."]


class RecordingLLM(CustomLLM):
    reply: str
    prompts: list = []

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata()

    def complete(self, prompt, formatted=False, **kwargs):
        self.prompts.append(prompt)
        return CompletionResponse(text=self.reply)

    def stream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError


class StructuredLLM(RecordingLLM):
    """Stands in for Claude's structured output: returns the asked verdict type and records every call."""
    reply: str = ""
    contained: dict = {}    # fact -> True / False, for FactVerdict
    aligned: bool = True    # for CorrectnessVerdict
    reason: str = "Same terms."
    calls: list = []

    async def astructured_predict(self, output_cls, prompt, llm_kwargs=None, **prompt_args):
        self.calls.append({"output_cls": output_cls, "prompt": prompt, "llm_kwargs": llm_kwargs, **prompt_args})
        if output_cls is FactVerdict:
            return FactVerdict(contained=self.contained[prompt_args["statement"]])
        return CorrectnessVerdict(reason=self.reason, aligned=self.aligned)

    def of(self, output_cls):
        return [call for call in self.calls if call["output_cls"] is output_cls]


class Correctness(unittest.TestCase):
    def judged(self, aligned, reason="Same package terms.", query=QUERY, response=OURS, reference=GOLD):
        llm = StructuredLLM(aligned=aligned, reason=reason, calls=[], prompts=[])
        judging = StructuredCorrectnessEvaluator(llm).aevaluate(query=query, response=response, reference=reference)
        return llm, asyncio.run(judging)

    def test_an_aligned_answer_passes_with_the_judges_reason(self):
        _, result = self.judged(True)
        self.assertTrue(result.passing)
        self.assertEqual((result.score, result.feedback), (1.0, "Same package terms."))

    def test_a_misaligned_answer_fails(self):
        _, result = self.judged(False, "Different incident.")
        self.assertFalse(result.passing)
        self.assertEqual((result.score, result.feedback), (0.0, "Different incident."))

    def test_one_structured_call_with_the_question_the_gold_answer_and_our_answer(self):
        llm, _ = self.judged(True)
        self.assertEqual(len(llm.calls), 1)
        call = llm.calls[0]
        self.assertIs(call["output_cls"], CorrectnessVerdict)
        self.assertIs(call["prompt"], CORRECTNESS_TEMPLATE)
        self.assertEqual((call["query"], call["reference_answer"], call["generated_answer"]), (QUERY, GOLD, OURS))
        self.assertEqual(call["llm_kwargs"], {"temperature": 0})

    def test_an_empty_question_answer_or_gold_answer_raises_before_any_call(self):
        for blank in ({"query": ""}, {"response": None}, {"reference": ""}):
            with self.assertRaises(ValueError):
                self.judged(True, **blank)

    def test_the_input_model_rejects_a_blank_field(self):
        with self.assertRaises(ValueError):
            CorrectnessCheck(question=QUERY, answer=OURS, gold_answer="")


class Completeness(unittest.TestCase):
    def judged(self, contained, response=OURS, facts=FACTS):
        llm = StructuredLLM(contained=dict(zip(FACTS, contained)), calls=[], prompts=[])
        return llm, asyncio.run(CompletenessEvaluator(llm).aevaluate(query=QUERY, response=response, facts=facts))

    def test_four_of_five_facts_is_eighty_percent_and_not_passing(self):
        _, result = self.judged([False, True, True, True, True])
        self.assertEqual(result.score, 0.8)
        self.assertFalse(result.passing)

    def test_every_fact_is_complete_and_passing(self):
        _, result = self.judged([True] * 5)
        self.assertEqual(result.score, 1.0)
        self.assertTrue(result.passing)

    def test_one_structured_call_per_fact_with_our_answer_and_that_fact_only(self):
        llm, _ = self.judged([True] * 5)
        self.assertEqual([call["statement"] for call in llm.calls], FACTS)
        for call in llm.calls:
            self.assertIs(call["output_cls"], FactVerdict)
            self.assertIs(call["prompt"], FACT_TEMPLATE)
            self.assertEqual(call["answer"], OURS)
            self.assertNotIn("query", call)  # the question is never sent

    def test_the_judge_is_asked_at_temperature_zero(self):
        llm, _ = self.judged([True] * 5)
        self.assertTrue(all(call["llm_kwargs"] == {"temperature": 0} for call in llm.calls))

    def test_the_verdict_of_each_fact_is_kept_in_order_for_audit(self):
        _, result = self.judged([False, True, True, True, True])
        verdicts = json.loads(result.feedback)
        self.assertEqual([verdict["fact"] for verdict in verdicts], FACTS)
        self.assertEqual([verdict["contained"] for verdict in verdicts], [False, True, True, True, True])

    def test_no_facts_raises_before_any_call(self):
        llm = StructuredLLM(calls=[], prompts=[])
        with self.assertRaises(ValueError):
            asyncio.run(CompletenessEvaluator(llm).aevaluate(query=QUERY, response=OURS, facts=[]))
        self.assertEqual(llm.calls, [])

    def test_an_empty_answer_raises_before_any_call(self):
        llm = StructuredLLM(calls=[], prompts=[])
        for empty in ("", None):
            with self.assertRaises(ValueError):
                asyncio.run(CompletenessEvaluator(llm).aevaluate(query=QUERY, response=empty, facts=FACTS))
        self.assertEqual(llm.calls, [])


class FactCheckInput(unittest.TestCase):
    def test_a_blank_fact_is_rejected(self):
        with self.assertRaises(ValueError):
            FactCheck(answer=OURS, facts=["a fact", ""])


NOT_FOUND_QUERY = "Which accounts are allowlisted, and what are their budget values?"  # as qst_0481: one fact
NOT_FOUND_GOLD = "The documents do not list the allowlisted accounts or their budgets."
NOT_FOUND_OURS = "The documents do not say which accounts are allowlisted."
NOT_FOUND_FACTS = ["The answer must state at some point that the query is not fully answerable from available documents."]


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


class Main(unittest.TestCase):
    """main() on two questions in temporary files, with a stand-in for Claude."""

    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.judgments = folder / "judgments" / "run.jsonl"
        self.llm = StructuredLLM(calls=[], prompts=[],
                                 contained={**{fact: True for fact in FACTS + NOT_FOUND_FACTS}, FACTS[0]: False})
        self.built = []  # the settings each Anthropic(...) was created with
        patches = [
            mock.patch.object(judge, "QUESTIONS", jsonl(folder / "questions.jsonl", [
                {"question_id": "qst_0009", "question": QUERY, "gold_answer": GOLD, "answer_facts": FACTS},
                {"question_id": "qst_0481", "question": NOT_FOUND_QUERY, "gold_answer": NOT_FOUND_GOLD,
                 "answer_facts": NOT_FOUND_FACTS}])),
            mock.patch.object(judge, "ANSWERS", jsonl(folder / "answers.jsonl", [
                {"question_id": "qst_0009", "answer": OURS, "document_ids": []},
                {"question_id": "qst_0481", "answer": NOT_FOUND_OURS, "document_ids": []}])),
            mock.patch.object(judge, "JUDGMENTS", self.judgments),
            mock.patch.object(judge, "Anthropic", lambda **settings: self.built.append(settings) or self.llm)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_main(self):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            asyncio.run(judge.main())
        return printed.getvalue()

    def rows(self):
        return [json.loads(line) for line in self.judgments.read_text().splitlines()]

    def test_every_answer_gets_one_row_in_the_official_scorers_format(self):
        self.run_main()
        self.assertEqual(self.rows()[0], {
            "question_id": "qst_0009", "answer_correct": True, "completeness_pct": 80.0, "reason": "Same terms.",
            "facts": [{"fact": fact, "contained": fact != FACTS[0]} for fact in FACTS]})
        self.assertEqual([(row["question_id"], row["completeness_pct"]) for row in self.rows()],
                         [("qst_0009", 80.0), ("qst_0481", 100.0)])

    def test_the_overall_score_is_printed(self):
        self.assertIn("overall score: 90.0", self.run_main())  # (1 x 80 + 1 x 100) / 2

    def test_the_correctness_call_of_each_question_holds_its_own_gold_answer(self):
        self.run_main()
        asked = {call["query"]: (call["reference_answer"], call["generated_answer"])
                 for call in self.llm.of(CorrectnessVerdict)}
        self.assertEqual(asked, {QUERY: (GOLD, OURS), NOT_FOUND_QUERY: (NOT_FOUND_GOLD, NOT_FOUND_OURS)})

    def test_the_fact_calls_of_each_question_hold_only_its_own_facts(self):
        self.run_main()
        asked = {answer: [call["statement"] for call in self.llm.of(FactVerdict) if call["answer"] == answer]
                 for answer in (OURS, NOT_FOUND_OURS)}
        self.assertEqual(asked, {OURS: FACTS, NOT_FOUND_OURS: NOT_FOUND_FACTS})

    def test_a_second_run_judges_nothing_and_keeps_the_rows(self):
        self.run_main()
        calls = len(self.llm.calls)
        self.assertEqual(calls, 2 + 6)  # 2 correctness calls, 5 + 1 fact calls
        self.run_main()
        self.assertEqual(len(self.llm.calls), calls)
        self.assertEqual(len(self.rows()), 2)

    def test_a_run_resumes_after_the_questions_already_judged(self):
        self.judgments.parent.mkdir(parents=True)
        jsonl(self.judgments, [{"question_id": "qst_0009", "answer_correct": True, "completeness_pct": 80.0}])
        self.run_main()
        self.assertEqual([row["question_id"] for row in self.rows()], ["qst_0009", "qst_0481"])
        self.assertEqual({call["query"] for call in self.llm.of(CorrectnessVerdict)}, {NOT_FOUND_QUERY})
        self.assertEqual({call["answer"] for call in self.llm.of(FactVerdict)}, {NOT_FOUND_OURS})

    def test_both_judges_are_haiku_at_temperature_zero(self):
        self.run_main()
        self.assertEqual(self.built, [{"model": "claude-haiku-4-5", "temperature": 0}] * 2)
        self.assertTrue(all(call["llm_kwargs"] == {"temperature": 0} for call in self.llm.calls))

    def test_no_plain_text_call_is_made(self):
        self.run_main()
        self.assertEqual(self.llm.prompts, [])


class TheBenchmarksPrompt(unittest.TestCase):
    def test_the_template_is_the_benchmarks_prompt_with_only_two_names_changed(self):
        official = runpy.run_path(str(BENCHMARK_PROMPTS))["ANSWER_WHOLISTIC_EVALUATION_PROMPT"]
        ours = (CORRECTNESS_TEMPLATE.template.replace("{reference_answer}", "{gold_answer}")
                .replace("{generated_answer}", "{candidate_answer}"))
        self.assertEqual(ours, official)

    def test_the_fact_template_is_the_benchmarks_fact_prompt_unchanged(self):
        self.assertEqual(FACT_TEMPLATE.template, runpy.run_path(str(BENCHMARK_PROMPTS))["INDIVIDUAL_FACT_VALIDATOR_PROMPT"])


class Doctests(unittest.TestCase):
    def test_doctests(self):
        for module in (judge, judge_prompts):
            self.assertEqual(doctest.testmod(module).failed, 0)


if __name__ == "__main__":
    unittest.main()

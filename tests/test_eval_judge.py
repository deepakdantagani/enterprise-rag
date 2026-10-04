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
from pipeline.eval.judge import CompletenessEvaluator, FactCheck, FactVerdict, aligned  # noqa: E402
from pipeline.eval.judge_prompts import CORRECTNESS_TEMPLATE, FACT_TEMPLATE  # noqa: E402
from llama_index.core.evaluation import CorrectnessEvaluator  # noqa: E402

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


class Aligned(unittest.TestCase):
    def test_yes_is_the_top_score_with_the_judges_reason(self):
        self.assertEqual(aligned('{"reason": "Same package terms.", "aligned": "yes"}'), (5.0, "Same package terms."))

    def test_no_is_the_bottom_score(self):
        self.assertEqual(aligned('{"reason": "Different incident.", "aligned": "no"}'), (1.0, "Different incident."))

    def test_json_inside_a_code_fence_is_read(self):
        self.assertEqual(aligned('```json\n{"reason": "ok", "aligned": "Yes"}\n```'), (5.0, "ok"))

    def test_a_reply_without_the_json_raises(self):
        with self.assertRaises(ValueError):
            aligned("I think it is aligned.")


class CorrectnessJudge(unittest.TestCase):
    def judged(self, reply):
        llm = RecordingLLM(reply=reply, prompts=[])
        judge_of = CorrectnessEvaluator(llm=llm, eval_template=CORRECTNESS_TEMPLATE, parser_function=aligned)
        result = asyncio.run(judge_of.aevaluate(query=QUERY, response=OURS, reference=GOLD))
        return llm, result

    def test_an_aligned_answer_passes_with_the_judges_reason(self):
        _, result = self.judged('{"reason": "Same package terms.", "aligned": "yes"}')
        self.assertTrue(result.passing)
        self.assertEqual(result.feedback, "Same package terms.")

    def test_a_misaligned_answer_fails(self):
        _, result = self.judged('{"reason": "Different incident.", "aligned": "no"}')
        self.assertFalse(result.passing)

    def test_the_judge_reads_the_question_the_gold_answer_and_our_answer_in_one_call(self):
        llm, _ = self.judged('{"reason": "ok", "aligned": "yes"}')
        self.assertEqual(len(llm.prompts), 1)
        for part in (QUERY, GOLD, OURS):
            self.assertIn(part, llm.prompts[0])

    def test_the_reply_format_reaches_the_judge_with_single_braces(self):
        llm, _ = self.judged('{"reason": "ok", "aligned": "yes"}')
        self.assertIn('{\n  "reason": "reason for the classification",\n  "aligned": "yes or no"\n}', llm.prompts[0])


class StructuredLLM(RecordingLLM):
    """Stands in for Claude's structured output: a FactVerdict per fact, every call recorded."""
    reply: str = ""
    contained: dict = {}
    calls: list = []

    async def astructured_predict(self, output_cls, prompt, llm_kwargs=None, **prompt_args):
        self.calls.append({"output_cls": output_cls, "prompt": prompt, "llm_kwargs": llm_kwargs, **prompt_args})
        return output_cls(contained=self.contained[prompt_args["statement"]])


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
        self.llm = StructuredLLM(reply='{"reason": "Same terms.", "aligned": "yes"}', calls=[], prompts=[],
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
        by_question = {QUERY: (GOLD, NOT_FOUND_GOLD), NOT_FOUND_QUERY: (NOT_FOUND_GOLD, GOLD)}
        self.assertEqual(len(self.llm.prompts), 2)
        for prompt in self.llm.prompts:
            own, other = next(golds for query, golds in by_question.items() if query in prompt)
            self.assertIn(own, prompt)
            self.assertNotIn(other, prompt)

    def test_the_fact_calls_of_each_question_hold_only_its_own_facts(self):
        self.run_main()
        asked = {answer: [call["statement"] for call in self.llm.calls if call["answer"] == answer]
                 for answer in (OURS, NOT_FOUND_OURS)}
        self.assertEqual(asked, {OURS: FACTS, NOT_FOUND_OURS: NOT_FOUND_FACTS})

    def test_a_second_run_judges_nothing_and_keeps_the_rows(self):
        self.run_main()
        calls = len(self.llm.calls) + len(self.llm.prompts)
        self.run_main()
        self.assertEqual(len(self.llm.calls) + len(self.llm.prompts), calls)
        self.assertEqual(len(self.rows()), 2)

    def test_a_run_resumes_after_the_questions_already_judged(self):
        self.judgments.parent.mkdir(parents=True)
        jsonl(self.judgments, [{"question_id": "qst_0009", "answer_correct": True, "completeness_pct": 80.0}])
        self.run_main()
        self.assertEqual([row["question_id"] for row in self.rows()], ["qst_0009", "qst_0481"])
        self.assertEqual({call["answer"] for call in self.llm.calls}, {NOT_FOUND_OURS})

    def test_the_judge_is_haiku_deterministic_with_short_replies(self):
        self.run_main()
        self.assertIn({"model": "claude-haiku-4-5", "temperature": 0, "max_tokens": 256}, self.built)
        self.assertTrue(all(settings["model"] == "claude-haiku-4-5" for settings in self.built))


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

import asyncio
import doctest
import runpy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata  # noqa: E402

from pipeline.eval import judge  # noqa: E402
from pipeline.eval.judge import CORRECTNESS_TEMPLATE, aligned, correctness_judge  # noqa: E402

BENCHMARK_PROMPTS = ROOT / "tests/fixtures/benchmark/answer_evaluation.py"  # the judge's prompt file, unchanged

# qst_0009
QUERY = ("In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
         "instead of matching the competitor's 50 percent first-year discount and migration credit?")
GOLD = "Redwood said it wouldn't match the competitor's 50% blanket Year-1 discount and $60k migration credit"
OURS = "Redwood proposed a 12-month commit package with the following components:"


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
        result = asyncio.run(correctness_judge(llm).aevaluate(query=QUERY, response=OURS, reference=GOLD))
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


class TheBenchmarksPrompt(unittest.TestCase):
    def test_the_template_is_the_benchmarks_prompt_with_only_two_names_changed(self):
        official = runpy.run_path(str(BENCHMARK_PROMPTS))["ANSWER_WHOLISTIC_EVALUATION_PROMPT"]
        ours = (CORRECTNESS_TEMPLATE.template.replace("{reference_answer}", "{gold_answer}")
                .replace("{generated_answer}", "{candidate_answer}"))
        self.assertEqual(ours, official)


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(judge).failed, 0)


if __name__ == "__main__":
    unittest.main()

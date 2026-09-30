"""RET-7: multi_query_retriever, v1's hybrid search for the question plus 3 LLM-written queries, fused by RRF.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.retrievers.fusion_retriever import QUERY_GEN_PROMPT

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import multi_query as multi_query_module  # noqa: E402
from pipeline.eval.hybrid import copy_to_hybrid, hybrid_store  # noqa: E402
from pipeline.eval.multi_query import (SavedCompletions, generated_queries, multi_query_retriever,  # noqa: E402
                                       query_prompt, save_completions, saved_completions)
from pipeline.eval.questions import Question  # noqa: E402
from tests.test_eval_hybrid import NODES, QuestionAt, source_with  # noqa: E402

PLANNED = "Roll back perf-canary\nperf-canary release\nroll back the release"
QUESTIONS = [Question("q1", "basic", ("slack",), "Who approved the Q3 budget?", ("dsid_a",)),
             Question("q2", "basic", ("slack",), "Where did the office move?", ("dsid_b",))]


class CountingLLM(CustomLLM):
    """Answers every prompt with PLANNED and counts the calls, standing in for the local planner."""
    calls: int = 0

    @property
    def metadata(self):
        return LLMMetadata()

    def complete(self, prompt, formatted=False, **kwargs):
        self.calls += 1
        return CompletionResponse(text=PLANNED)

    def stream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError


class SaveCompletions(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "gemma4.jsonl"

    def test_each_question_is_planned_once_and_saved_with_its_prompt(self):
        llm = CountingLLM()
        self.assertEqual(save_completions(QUESTIONS, llm, self.out), 2)
        rows = [json.loads(line) for line in self.out.read_text().splitlines()]
        self.assertEqual((llm.calls, [row["question_id"] for row in rows]), (2, ["q1", "q2"]))
        self.assertEqual((rows[0]["prompt"], rows[0]["completion"]), (query_prompt(QUESTIONS[0].text), PLANNED))

    def test_a_rerun_plans_nothing_new(self):
        save_completions(QUESTIONS, CountingLLM(), self.out)
        llm = CountingLLM()
        self.assertEqual((save_completions(QUESTIONS, llm, self.out), llm.calls), (0, 0))

    def test_another_prompt_is_saved_as_sent(self):
        save_completions(QUESTIONS[:1], CountingLLM(), self.out, prompt="Rephrase {num_queries}x: {query}")
        self.assertEqual(json.loads(self.out.read_text())["prompt"], "Rephrase 3x: Who approved the Q3 budget?")

    def test_the_saved_completions_replay_without_the_llm(self):
        save_completions(QUESTIONS, CountingLLM(), self.out)
        self.assertEqual(saved_completions(self.out).complete(query_prompt(QUESTIONS[1].text)).text, PLANNED)

    def test_a_prompt_that_was_not_saved_names_it(self):
        with self.assertRaisesRegex(KeyError, "Who moved"):
            SavedCompletions({}).complete(query_prompt("Who moved?"))


class NearBerlinUnlessGenerated(QuestionAt):
    """The question's vector is nearest Berlin; the generated queries' vectors are nearest the runbook."""
    def _get_query_embedding(self, query):
        return [0.3, 0.2, 0.3, 0.4] if query.startswith("Who") else [-1.0, 0.0, 0.0, 0.0]


class MultiQueryRetriever(unittest.TestCase):
    def setUp(self):
        client = source_with(NODES)
        self.store = hybrid_store(client, "hybrid")
        copy_to_hybrid(client, "v0", self.store)
        self.llm = SavedCompletions({query_prompt("Who approved the Q3 budget?"): PLANNED})

    def test_uses_llamaindexs_default_prompt_for_the_question_and_3_queries(self):
        retriever = multi_query_retriever(self.store, QuestionAt(embed_dim=4), self.llm)
        self.assertEqual((retriever.query_gen_prompt, retriever.num_queries, retriever.mode),
                         (QUERY_GEN_PROMPT, 4, "reciprocal_rerank"))
        self.assertEqual(generated_queries(retriever, "Who approved the Q3 budget?"), PLANNED.split("\n"))

    def test_another_prompt_is_sent_and_saved_prompts_replay_under_it(self):
        prompt = "Write {num_queries} versions of: {query}\n"
        llm = SavedCompletions({query_prompt("Who approved the Q3 budget?", prompt): "Q3 budget approver"})
        retriever = multi_query_retriever(self.store, QuestionAt(embed_dim=4), llm, prompt=prompt)
        self.assertEqual(query_prompt("Who?", prompt), "Write 3 versions of: Who?\n")
        self.assertEqual(generated_queries(retriever, "Who approved the Q3 budget?"), ["Q3 budget approver"])

    def test_a_chunk_only_the_generated_queries_find_is_returned(self):
        # the question alone: dense Berlin, BM25 the budget; each of the 3 generated queries: the runbook, twice
        retriever = multi_query_retriever(self.store, NearBerlinUnlessGenerated(embed_dim=4), self.llm, top_k=1)
        found = [one.node.text for one in retriever.retrieve("Who approved the Q3 budget?")]
        self.assertEqual(found, ["Roll back the perf-canary release."])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(multi_query_module).failed, 0)


PLANNER_FILE = ROOT / "data/_index/planner/gemma4-26b.jsonl"


@unittest.skipUnless(PLANNER_FILE.is_file(), "needs data/_index/planner")
class RealPlanner(unittest.TestCase):
    def test_every_scored_question_has_a_saved_plan(self):
        self.assertEqual(len(PLANNER_FILE.read_text().splitlines()), 470)


if __name__ == "__main__":
    unittest.main()

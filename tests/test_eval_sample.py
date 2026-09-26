"""EVAL-3d2: sample_corpus, a small corpus from every source to try the baseline in a minute.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import sample as sample_module  # noqa: E402
from pipeline.eval.questions import Question, load_questions  # noqa: E402
from pipeline.eval.sample import sample_corpus  # noqa: E402

DOCUMENTS = ROOT / "data/_full/documents.parquet"
QUESTIONS = ROOT / "data/_full/questions.jsonl"
SLACK_1 = Question("q1", "basic", ("slack",), "…", ("s1",))
SLACK_2 = Question("q2", "basic", ("slack",), "…", ("s2",))
JIRA = Question("q3", "basic", ("jira",), "…", ("j1", "j2"))
BOTH = Question("q4", "semantic", ("slack", "jira"), "…", ("s3", "j3"))
SOURCES = {"s1": "slack", "s2": "slack", "s3": "slack", "s4": "slack", "s5": "slack",
           "j1": "jira", "j2": "jira", "j3": "jira", "j4": "jira", "j5": "jira"}


class SampleCorpus(unittest.TestCase):
    def test_takes_the_first_single_source_questions_of_each_source(self):
        questions, _ = sample_corpus([SLACK_1, BOTH, SLACK_2, JIRA], SOURCES, questions_per_source=1, others_per_source=0)
        self.assertEqual(questions, [JIRA, SLACK_1])

    def test_keeps_every_expected_doc_plus_others_from_each_source(self):
        _, doc_ids = sample_corpus([SLACK_1, JIRA], SOURCES, questions_per_source=1, others_per_source=2)
        self.assertTrue({"s1", "j1", "j2"} <= doc_ids)
        self.assertEqual(sum(1 for d in doc_ids if SOURCES[d] == "slack"), 3)
        self.assertEqual(sum(1 for d in doc_ids if SOURCES[d] == "jira"), 4)

    def test_same_seed_same_sample(self):
        runs = [sample_corpus([SLACK_1, JIRA], SOURCES, 1, 2, seed=7) for _ in range(2)]
        self.assertEqual(runs[0], runs[1])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(sample_module).failed, 0)


@unittest.skipUnless(DOCUMENTS.is_file() and QUESTIONS.is_file(), "needs data/_full")
class RealSample(unittest.TestCase):
    def test_27_questions_and_207_documents_from_all_9_sources(self):
        table = pq.read_table(DOCUMENTS, columns=["doc_id", "source_type"])
        sources = dict(zip(table["doc_id"].to_pylist(), table["source_type"].to_pylist()))
        questions, doc_ids = sample_corpus(load_questions(QUESTIONS).questions, sources)
        self.assertEqual((len(questions), len(doc_ids)), (27, 207))
        self.assertEqual(len({sources[d] for d in doc_ids}), 9)


if __name__ == "__main__":
    unittest.main()

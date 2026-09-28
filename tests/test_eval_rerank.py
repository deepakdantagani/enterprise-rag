"""RET-5: rerank_saved and replay_retriever, v1's top 50 reranked once per question and replayed for $0.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import rerank as rerank_module  # noqa: E402
from pipeline.eval.rerank import rerank_saved, replay_retriever, voyage_rerank  # noqa: E402

RERANK_DIR = ROOT / "data/_index/rerank"
CANDIDATES = [
    {"question_id": "q1", "question": "Who approved the Q3 budget?", "candidates": [
        {"node_id": "c1", "ref_doc_id": "dsid_berlin", "text": "The Berlin office moved."},
        {"node_id": "c2", "ref_doc_id": "dsid_budget", "text": "Priya approved the Q3 budget."}]},
    {"question_id": "q2", "question": "Roll back perf-canary?", "candidates": [
        {"node_id": "c3", "ref_doc_id": "dsid_runbook", "text": "Roll back the perf-canary release."}]},
]


def candidates_file():
    path = Path(tempfile.mkdtemp()) / "v1_candidates.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in CANDIDATES))
    return path


class ByWords:
    """Stands in for a reranker: scores a text by how many question words it shares, counts calls."""
    def __init__(self):
        self.calls = 0

    def __call__(self, question, texts):
        self.calls += 1
        words = set(question.lower().strip("?").split())
        scores = [len(words & set(text.lower().strip(".").split())) / 10 for text in texts]
        order = sorted(range(len(texts)), key=lambda i: -scores[i])
        return order, [scores[i] for i in order], 7 * len(texts)


class RerankSaved(unittest.TestCase):
    def setUp(self):
        self.candidates = candidates_file()
        self.out = self.candidates.parent / "fake-model.jsonl"

    def test_each_question_is_reranked_once_and_saved(self):
        reranker = ByWords()
        self.assertEqual(rerank_saved(self.candidates, self.out, reranker), 21)  # tokens: 7 x 3 texts
        rows = [json.loads(line) for line in self.out.read_text().splitlines()]
        self.assertEqual((reranker.calls, [row["question_id"] for row in rows]), (2, ["q1", "q2"]))
        self.assertEqual(rows[0]["order"], [1, 0])

    def test_a_rerun_reranks_nothing_new(self):
        rerank_saved(self.candidates, self.out, ByWords())
        reranker = ByWords()
        self.assertEqual((rerank_saved(self.candidates, self.out, reranker), reranker.calls), (0, 0))


class ReplayRetriever(unittest.TestCase):
    def setUp(self):
        self.candidates = candidates_file()
        self.out = self.candidates.parent / "fake-model.jsonl"
        rerank_saved(self.candidates, self.out, ByWords())

    def docs(self, retriever, question):
        return [found.node.ref_doc_id for found in retriever.retrieve(question)]

    def test_without_a_rerank_file_the_candidates_come_back_as_retrieved(self):
        self.assertEqual(self.docs(replay_retriever(self.candidates), "Who approved the Q3 budget?"),
                         ["dsid_berlin", "dsid_budget"])

    def test_with_a_rerank_file_they_come_back_in_the_reranked_order(self):
        found = replay_retriever(self.candidates, self.out).retrieve("Who approved the Q3 budget?")
        self.assertEqual([(one.node.ref_doc_id, one.node.node_id) for one in found],
                         [("dsid_budget", "c2"), ("dsid_berlin", "c1")])
        self.assertGreater(found[0].score, found[1].score)

    def test_a_question_that_was_not_saved_names_it(self):
        with self.assertRaisesRegex(KeyError, "Who moved"):
            replay_retriever(self.candidates).retrieve("Who moved?")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(rerank_module).failed, 0)


class VoyageRerank(unittest.TestCase):
    def test_turns_voyages_answer_into_order_scores_and_tokens(self):
        answer = SimpleNamespace(total_tokens=23366, results=[SimpleNamespace(index=2, relevance_score=0.934),
                                                              SimpleNamespace(index=0, relevance_score=0.922)])
        client = SimpleNamespace(rerank=lambda query, documents, model: answer)
        self.assertEqual(voyage_rerank(client, "rerank-3")("q", ["a", "b", "c"]), ([2, 0], [0.934, 0.922], 23366))


@unittest.skipUnless((RERANK_DIR / "rerank-3-lite.jsonl").is_file(), "needs data/_index/rerank")
class RealRerank(unittest.TestCase):
    def test_rerank_3_lite_puts_qst_0001s_third_candidate_first(self):
        row = json.loads((RERANK_DIR / "v1_candidates.jsonl").read_text().split("\n", 1)[0])
        found = replay_retriever(RERANK_DIR / "v1_candidates.jsonl", RERANK_DIR / "rerank-3-lite.jsonl").retrieve(
            row["question"])
        self.assertEqual((len(found), found[0].node.node_id), (50, row["candidates"][2]["node_id"]))


if __name__ == "__main__":
    unittest.main()

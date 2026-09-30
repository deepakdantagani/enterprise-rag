"""GEN-5: answer_run, the first answer file over all 500 questions on local gemma4:26b.

Run: uv run python -m unittest tests.test_eval_answer_run
"""
import doctest
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.eval import answer_run  # noqa: E402
from pipeline.eval.answer_run import ANSWERS, batches, top_ten_ids  # noqa: E402
from pipeline.eval.questions import Question  # noqa: E402
from pipeline.eval.rerank import ReplayRetriever  # noqa: E402


class TopTenIds(unittest.TestCase):
    def test_every_document_any_question_will_read_once(self):
        saved = {"Who?": {"question_id": "q1", "question": "Who?", "candidates": [
                     {"node_id": "c1", "ref_doc_id": "dsid_a", "text": "."}, {"node_id": "c2", "ref_doc_id": "dsid_b", "text": "."}]},
                 "When?": {"question_id": "q2", "question": "When?", "candidates": [
                     {"node_id": "c3", "ref_doc_id": "dsid_b", "text": "."}]}}
        questions = [Question("q1", "simple", (), "Who?", ()), Question("q2", "simple", (), "When?", ())]
        self.assertEqual(top_ten_ids(ReplayRetriever(saved), questions), {"dsid_a", "dsid_b"})


@unittest.skipUnless(ANSWERS.is_file(), "no answer file yet")
class RealAnswers(unittest.TestCase):
    def test_500_rows_each_with_an_answer_and_10_documents(self):
        rows = [json.loads(line) for line in ANSWERS.read_text().splitlines()]
        self.assertEqual((len(rows), len({row["question_id"] for row in rows})), (500, 500))
        self.assertEqual([row["question_id"] for row in rows if not row["answer"] or len(row["document_ids"]) != 10], [])


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(answer_run).failed, 0)


if __name__ == "__main__":
    unittest.main()

"""EVAL-2a: load_questions, the benchmark questions that have expected docs, as typed records.

Run: uv run python -m unittest discover tests
"""
import doctest
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import questions as questions_module  # noqa: E402
from pipeline.eval.questions import Question, load_questions  # noqa: E402

QUESTIONS = ROOT / "data/_full/questions.jsonl"
QUESTIONS_SHA256 = "f9524b9157cd43aae36b99333a124738804306ea6d07f332d49faa6d3d147905"
ROW = {"question_id": "qst_0431", "question_type": "completeness", "source_types": ["confluence"],
       "question": "What is the procedure for an emergency rollback?", "expected_doc_ids": ["dsid_f6e3", "dsid_8407"],
       "gold_answer": "…", "answer_facts": ["…"]}
NO_DOCS = dict(ROW, question_id="qst_0471", question_type="info_not_found", source_types=[], expected_doc_ids=[])


def load_rows(*rows):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "questions.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return load_questions(path)


class LoadQuestions(unittest.TestCase):
    def test_a_row_with_expected_docs_becomes_a_question(self):
        self.assertEqual(load_rows(ROW).questions, [Question(
            "qst_0431", "completeness", ("confluence",), "What is the procedure for an emergency rollback?",
            ("dsid_f6e3", "dsid_8407"))])

    def test_a_row_with_no_expected_docs_is_skipped_and_counted(self):
        loaded = load_rows(ROW, NO_DOCS)
        self.assertEqual([q.question_id for q in loaded.questions], ["qst_0431"])
        self.assertEqual(loaded.skipped, 1)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(questions_module).failed, 0)


@unittest.skipUnless(QUESTIONS.is_file(), "needs data/_full/questions.jsonl")
class RealQuestions(unittest.TestCase):
    def test_the_answer_key_is_the_one_we_measured(self):
        self.assertEqual(hashlib.sha256(QUESTIONS.read_bytes()).hexdigest(), QUESTIONS_SHA256)

    def test_470_questions_are_scored_and_30_skipped(self):
        loaded = load_questions(QUESTIONS)
        self.assertEqual((len(loaded.questions), loaded.skipped), (470, 30))


if __name__ == "__main__":
    unittest.main()

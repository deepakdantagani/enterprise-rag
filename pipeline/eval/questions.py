"""EVAL-2a: load_questions, the benchmark questions that have expected docs, as typed records.

`data/_full/questions.jsonl` holds the benchmark's 500 questions. 30 of them expect no
document (all 20 info_not_found and all 10 high_level, e.g. qst_0471): document recall has
nothing to count for them, so they are left out and counted, and every run scores the same
470. `gold_answer` and `answer_facts` are for answer scoring, so they are not read here.

    >>> row = '{"question_id": "qst_0431", "question_type": "completeness", "source_types": ["confluence"], '
    >>> row += '"question": "Emergency rollback?", "expected_doc_ids": ["dsid_f6e3", "dsid_8407"]}'
    >>> question_from_row(row)
    Question(question_id='qst_0431', question_type='completeness', source_types=('confluence',), text='Emergency rollback?', expected_doc_ids=('dsid_f6e3', 'dsid_8407'))
"""
import json
from pathlib import Path
from typing import List, NamedTuple, Tuple


class Question(NamedTuple):
    question_id: str
    question_type: str
    source_types: Tuple[str, ...]
    text: str
    expected_doc_ids: Tuple[str, ...]


class LoadedQuestions(NamedTuple):
    questions: List[Question]
    skipped: int  # questions with no expected docs


def question_from_row(line: str) -> Question:
    row = json.loads(line)
    return Question(row["question_id"], row["question_type"], tuple(row["source_types"]),
                    row["question"], tuple(row["expected_doc_ids"]))


def load_questions(path: Path) -> LoadedQuestions:
    every_question = [question_from_row(line) for line in Path(path).read_text().splitlines() if line.strip()]
    scored = [question for question in every_question if question.expected_doc_ids]
    return LoadedQuestions(scored, len(every_question) - len(scored))

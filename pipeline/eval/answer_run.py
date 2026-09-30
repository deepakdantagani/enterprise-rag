"""GEN-5: answer_run, the first answer file over all 500 questions on local gemma4:26b.

The leaderboard scores an answer file, one line per question (GEN-1). This run replays v4's saved
top 100 in its rerank-3-lite order for all 500 questions (GEN-4 added the 30 with no expected
documents, e.g. qst_0481, info_not_found), reads the 10 whole documents of every question from
the corpus in one pass (GEN-2b: one 1.2 s scan, not 500), and answers with ANSWER_PROMPT on
gemma4:26b ($0, ~10 s a question). save_answers makes it resumable: re-run the same command after
a crash. Progress goes to the run log as one StageDone per batch of 10.

    >>> [len(batch) for batch in batches(list(range(23)), 10)]
    [10, 10, 3]

Run: uv run python -m pipeline.eval.answer_run
"""
import time
from pathlib import Path
from typing import List, Sequence, Set

from llama_index.core.base.base_retriever import BaseRetriever

from pipeline.eval.answers import first_documents

ROOT = Path(__file__).resolve().parents[2]
ANSWERS = ROOT / "data/_index/answers/v4-gemma4-base.jsonl"
BATCH = 10


def batches(items: Sequence, size: int) -> List[Sequence]:
    return [items[start:start + size] for start in range(0, len(items), size)]


def top_ten_ids(retriever: BaseRetriever, questions: Sequence) -> Set[str]:
    """Every document any question's top 10 will show, so the corpus is read once."""
    return {doc_id for question in questions for doc_id in first_documents(retriever.retrieve(question.text))}


def main() -> None:
    from pipeline.eval.answers import answer_engine, answerer_llm, documents_by_id, save_answers
    from pipeline.eval.missing import CANDIDATES, QUESTIONS, V4_ORDER
    from pipeline.eval.questions import all_questions
    from pipeline.eval.rerank import replay_retriever
    from pipeline.observability import PipelineEvent, StageDone, dispatcher, events_logged_to
    questions, retriever = all_questions(QUESTIONS), replay_retriever(CANDIDATES, V4_ORDER)
    ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with events_logged_to(ANSWERS.with_suffix(".events.jsonl"), only=PipelineEvent):
        started = time.time()
        documents = documents_by_id(ROOT / "data/_full/documents.parquet", sorted(top_ten_ids(retriever, questions)))
        dispatcher.event(StageDone(source="all", stage="documents", files=len(documents), failed=0,
                                   seconds=time.time() - started))
        engine = answer_engine(retriever, answerer_llm(), documents)
        for number, batch in enumerate(batches(questions, BATCH), 1):
            started = time.time()
            answered = save_answers(engine, batch, ANSWERS)
            dispatcher.event(StageDone(source="all", stage=f"answers {number * BATCH}/{len(questions)}", files=answered,
                                       failed=0, seconds=time.time() - started))


if __name__ == "__main__":
    main()

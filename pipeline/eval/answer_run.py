"""GEN-5: answer_run, the first answer file over all 500 questions on local gemma4:26b.

The leaderboard scores an answer file, one line per question (GEN-1). This run replays v4's saved
top 100 in its rerank-3-lite order for all 500 questions (GEN-4 added the 30 with no expected
documents, e.g. qst_0481, info_not_found), reads the 10 whole documents of every question from
the corpus in one pass (GEN-2b: one 1.2 s scan, not 500), and answers with PROMPT (v2 since GEN-10a, v3 since GEN-13d) on
the answerer (GEN-5: gemma4:26b, $0, ~10 s a question; GEN-12a: deepseek-v4-pro, paid). save_answers makes it resumable: re-run the same command after
a crash. Progress goes to the run log as one StageDone per batch of 10.

    >>> [len(batch) for batch in batches(list(range(23)), 10)]
    [10, 10, 3]

Run: uv run python -m pipeline.eval.answer_run
"""
import time
from pathlib import Path
from typing import List, Sequence, Set

from llama_index.core.base.base_retriever import BaseRetriever

from pipeline.eval.answers import ANSWER_PROMPT_V3, deepseek_answerer_llm, first_documents

ROOT = Path(__file__).resolve().parents[2]
ANSWERER_LLM = deepseek_answerer_llm  # GEN-12a: the model that answers; answerer_llm is the local gemma4:26b
PROMPT = ANSWER_PROMPT_V3  # GEN-13d: documents in tags with their source, quotes before the answer
ANSWERS = ROOT / "data/_index/answers/v4-deepseek-v4-pro-v3.jsonl"  # prompt v2: v4-deepseek-v4-pro-v2.jsonl, v4-gemma4-v2.jsonl (v1: v4-gemma4-base.jsonl)
BATCH = 10


def batches(items: Sequence, size: int) -> List[Sequence]:
    return [items[start:start + size] for start in range(0, len(items), size)]


def top_ten_ids(retriever: BaseRetriever, questions: Sequence) -> Set[str]:
    """Every document any question's top 10 will show, so the corpus is read once."""
    return {doc_id for question in questions for doc_id in first_documents(retriever.retrieve(question.text))}


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")  # DEEPSEEK_API_KEY
    from pipeline.eval.answers import answer_engine, documents_by_id, save_answers, sources_by_id
    from pipeline.eval.missing import CANDIDATES, QUESTIONS, V4_ORDER
    from pipeline.eval.questions import all_questions
    from pipeline.eval.rerank import replay_retriever
    from pipeline.observability import PipelineEvent, StageDone, dispatcher, events_logged_to
    questions, retriever = all_questions(QUESTIONS), replay_retriever(CANDIDATES, V4_ORDER)
    ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with events_logged_to(ANSWERS.with_suffix(".events.jsonl"), only=PipelineEvent):
        started = time.time()
        doc_ids = sorted(top_ten_ids(retriever, questions))
        documents = documents_by_id(ROOT / "data/_full/documents.parquet", doc_ids)
        sources = sources_by_id(ROOT / "data/_full/documents.parquet", doc_ids)
        dispatcher.event(StageDone(source="all", stage="documents", files=len(documents), failed=0,
                                   seconds=time.time() - started))
        engine = answer_engine(retriever, ANSWERER_LLM(), documents, prompt=PROMPT, sources=sources)
        for number, batch in enumerate(batches(questions, BATCH), 1):
            started = time.time()
            answered = save_answers(engine, batch, ANSWERS)
            dispatcher.event(StageDone(source="all", stage=f"answers {number * BATCH}/{len(questions)}", files=answered,
                                       failed=0, seconds=time.time() - started))


if __name__ == "__main__":
    main()

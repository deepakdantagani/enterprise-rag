"""GEN-4: save_query_vectors and save_candidates, v4's retrieval for the 30 questions never saved.

v4's top 100 and its rerank were saved for the 470 questions with expected documents only
(EVAL-2a skips the rest), but the leaderboard averages over all 500 (GEN-3): qst_0481
(info_not_found) and qst_0471 ("What is Redwood Inference's mission statement?", high_level) had
no candidates, so the replay retriever could not answer them. Each step appends only what is
missing, in the saved row formats, so the 470 saved rows stay byte-identical: the question
vectors (voyage-4, input_type "query"), then the live top 100 (GEN-8a), then rerank_saved.

    >>> candidates_row("q1", "Who?", [])
    {'question_id': 'q1', 'question': 'Who?', 'candidates': []}
"""
import json
from pathlib import Path
from typing import Callable, List, Sequence, Set, Union

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import NodeWithScore

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/_full/questions.jsonl"
VECTORS = ROOT / "data/_index/question_embeddings/voyage-4.jsonl"
CANDIDATES = ROOT / "data/_index/rerank/lite_titles_top100_candidates.jsonl"
V4_ORDER = ROOT / "data/_index/rerank/lite-titles-top100-rerank-3-lite.jsonl"


def candidates_row(question_id: str, question: str, found: List[NodeWithScore]) -> dict:
    """One saved top-100 row; text is the plain chunk text, as rerank-3-lite reads it."""
    return {"question_id": question_id, "question": question,
            "candidates": [{"node_id": chunk.node.node_id, "ref_doc_id": chunk.node.ref_doc_id, "text": chunk.node.text}
                           for chunk in found]}


def append_missing(questions: Sequence, out_path: Union[str, Path], row_of: Callable) -> int:
    """Append row_of(question) for every question not yet in `out_path`; returns how many."""
    out_path = Path(out_path)
    done: Set[str] = {json.loads(line)["question_id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    added = 0
    with out_path.open("a") as out:
        for question in questions:
            if question.question_id not in done:
                out.write(json.dumps(row_of(question)) + "\n")
                out.flush()
                added += 1
    return added


def save_query_vectors(embed_model: BaseEmbedding, model: str, questions: Sequence, out_path: Union[str, Path]) -> int:
    return append_missing(questions, out_path, lambda q: {"question_id": q.question_id, "text": q.text, "model": model,
                                                          "input_type": "query",
                                                          "embedding": embed_model.get_query_embedding(q.text)})


def save_candidates(retriever: BaseRetriever, questions: Sequence, out_path: Union[str, Path]) -> int:
    return append_missing(questions, out_path, lambda q: candidates_row(q.question_id, q.text, retriever.retrieve(q.text)))


def main() -> None:  # uv run python -m pipeline.eval.missing  (paid: ~$0.001 of voyage-4, rerank from the free pool)
    import os
    import time

    import voyageai
    from dotenv import load_dotenv
    from qdrant_client import QdrantClient

    from pipeline.eval.answers import RERANKER, live_retriever
    from pipeline.eval.embedders import embed_model_named, saved_query_embeddings
    from pipeline.eval.questions import all_questions
    from pipeline.eval.rerank import rerank_saved, voyage_rerank
    from pipeline.observability import PipelineEvent, StageDone, dispatcher, events_logged_to
    load_dotenv(ROOT / ".env")
    key, questions = os.environ.get("VOYAGE_API_KEY"), all_questions(QUESTIONS)
    steps = [("query vectors", lambda: save_query_vectors(embed_model_named("voyage-4", voyage_api_key=key), "voyage-4",
                                                          questions, VECTORS)),
             ("candidates", lambda: save_candidates(  # no fallback: every question has a saved vector by now
                 live_retriever(QdrantClient(url="http://localhost:6333", timeout=600), saved_query_embeddings(VECTORS)),
                 questions, CANDIDATES)),
             ("rerank tokens", lambda: rerank_saved(CANDIDATES, V4_ORDER, voyage_rerank(voyageai.Client(api_key=key), RERANKER)))]
    with events_logged_to(ROOT / "data/_index/rerank/gen-4-events.jsonl", only=PipelineEvent):
        for stage, run in steps:
            started = time.time()
            dispatcher.event(StageDone(source="all", stage=stage, files=run(), failed=0, seconds=time.time() - started))


if __name__ == "__main__":
    main()

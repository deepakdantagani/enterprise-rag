"""RET-5: rerank_saved and replay_retriever, v1's top 50 reranked once per question and replayed.

v1 (RET-4) finds a relevant document in its top 20 for recall 0.791 but in its top 10 for only
0.722: right documents are retrieved and ranked too low. A cross-encoder reranker reads the
question and each of the 50 chunks together and re-sorts them. It is paid per call (Voyage bills
query tokens × 50 + the 50 chunks: 23,366 tokens for qst_0001), and the scorer asks each
question three times (k = 5, 10, 20), so the top 50 is saved once (v1_candidates.jsonl), each
question is reranked once per model (<model>.jsonl, resumable), and scoring replays the saved
order for $0. On qst_0001 rerank-3-lite moves v1's third chunk to first.

    >>> saved = {"question_id": "q1", "question": "Who approved the Q3 budget?", "candidates": [
    ...     {"node_id": "c1", "ref_doc_id": "dsid_berlin", "text": "The Berlin office moved."},
    ...     {"node_id": "c2", "ref_doc_id": "dsid_budget", "text": "Priya approved the Q3 budget."}]}
    >>> retriever = ReplayRetriever({"Who approved the Q3 budget?": saved}, {"q1": ([1, 0], [0.9, 0.1])})
    >>> [found.node.ref_doc_id for found in retriever.retrieve("Who approved the Q3 budget?")]
    ['dsid_budget', 'dsid_berlin']
"""
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeRelationship, NodeWithScore, QueryBundle, RelatedNodeInfo, TextNode

Order = Tuple[List[int], List[float]]  # candidate indexes best first, and their scores
Reranker = Callable[[str, Sequence[str]], Tuple[List[int], List[float], int]]  # -> order, scores, tokens


def read_jsonl(path: Union[str, Path]) -> List[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def rerank_saved(candidates_path: Union[str, Path], out_path: Union[str, Path], rerank: Reranker) -> int:
    """Rerank every saved question not yet in `out_path`; returns the tokens this call used."""
    out_path = Path(out_path)
    done = {row["question_id"] for row in read_jsonl(out_path)} if out_path.exists() else set()
    tokens = 0
    with out_path.open("a") as out:
        for row in read_jsonl(candidates_path):
            if row["question_id"] in done:
                continue
            order, scores, used = rerank(row["question"], [candidate["text"] for candidate in row["candidates"]])
            out.write(json.dumps({"question_id": row["question_id"], "order": order, "scores": scores,
                                  "tokens": used}) + "\n")
            out.flush()
            tokens += used
    return tokens


def voyage_rerank(client, model: str) -> Reranker:
    def rerank(question: str, texts: Sequence[str]) -> Tuple[List[int], List[float], int]:
        answer = client.rerank(query=question, documents=list(texts), model=model)
        return ([one.index for one in answer.results], [one.relevance_score for one in answer.results],
                answer.total_tokens)
    return rerank


class ReplayRetriever(BaseRetriever):
    """A saved question's candidates, in the saved rerank order (or as first retrieved)."""

    def __init__(self, by_question: Dict[str, dict], orders: Optional[Dict[str, Order]] = None) -> None:
        super().__init__()
        self._by_question, self._orders = by_question, orders or {}

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        if query_bundle.query_str not in self._by_question:
            raise KeyError(f"no saved candidates for {query_bundle.query_str!r}")
        row = self._by_question[query_bundle.query_str]
        count = len(row["candidates"])
        order, scores = self._orders.get(row["question_id"], (list(range(count)), [1 / (rank + 1) for rank in range(count)]))
        return [NodeWithScore(node=TextNode(id_=row["candidates"][i]["node_id"], text=row["candidates"][i]["text"],
                                            relationships={NodeRelationship.SOURCE: RelatedNodeInfo(
                                                node_id=row["candidates"][i]["ref_doc_id"])}),
                              score=score)
                for i, score in zip(order, scores)]


def replay_retriever(candidates_path: Union[str, Path], rerank_path: Optional[Union[str, Path]] = None) -> ReplayRetriever:
    by_question = {row["question"]: row for row in read_jsonl(candidates_path)}
    orders = {row["question_id"]: (row["order"], row["scores"]) for row in read_jsonl(rerank_path)} if rerank_path else None
    return ReplayRetriever(by_question, orders)

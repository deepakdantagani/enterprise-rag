"""EVAL-1: document_recall, the leaderboard's document recall for one question.

The share of a question's expected docs found in the first k distinct retrieved docs. A
retriever ranks chunks, and one document can fill several places: a long Gmail thread cut
into 512-token chunks could take all ten. So chunks collapse to their document first, in rank
order, and only then is the list cut at k.

Real example: qst_0431 (completeness) expects two docs, dsid_f6e3b7ad... and dsid_840703a1...;
a top 10 holding only the first scores 0.5. The 30 questions with no expected docs
(info_not_found, high_level) score None and stay out of the average.

The arithmetic is LlamaIndex's Recall metric; this adds the collapse, the cut and the None.

    >>> document_recall(["dsid_a", "dsid_a", "dsid_b"], ["dsid_b", "dsid_c"], k=2)
    0.5
    >>> document_recall(["dsid_a"], []) is None
    True
"""
from typing import Optional, Sequence

from llama_index.core.evaluation.retrieval.metrics import Recall


def document_recall(ranked_doc_ids: Sequence[str], expected_doc_ids: Sequence[str], k: int = 10) -> Optional[float]:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    if not expected_doc_ids:
        return None
    if not ranked_doc_ids:
        return 0.0
    top_k = list(dict.fromkeys(ranked_doc_ids))[:k]
    return Recall().compute(expected_ids=list(expected_doc_ids), retrieved_ids=top_k).score

"""EVAL-3c: score_retriever, every question at every k, scored in one event loop.

The loop between a retriever and the report: each of the 470 questions, at k = 5, 10 and 20,
through DocumentRetrieverEvaluator (EVAL-1), as the Scored rows metrics_report (EVAL-2b) takes.

Why one event loop: evaluator.evaluate() starts a new loop per call, and the first sample run
against Qdrant failed on the second question with "Event loop is closed", because the async
Qdrant client stays bound to the loop it was first used in. So every question is awaited with
aevaluate() inside a single asyncio.run.

EVAL-3h adds precision: relevant documents over the documents returned (at most k, fewer when
the retrieved chunks hold fewer distinct documents). 377 of the 470 questions have one relevant
document, so their precision@10 can never pass 0.1: read it to compare runs, not as a grade.

    >>> from llama_index.core import Document, SummaryIndex
    >>> from pipeline.eval.questions import Question
    >>> index = SummaryIndex.from_documents([Document(id_="dsid_a", text="Roll back."), Document(id_="dsid_b", text="Pin.")])
    >>> question = Question("qst_0431", "completeness", ("confluence",), "Emergency rollback?", ("dsid_b",))
    >>> [(one.k, one.metrics["recall"], one.metrics["mrr"]) for one in score_retriever(index.as_retriever(), [question], ks=(1, 2))]
    [(1, 0.0, 0.0), (2, 1.0, 0.5)]
"""
import asyncio
from typing import List, Sequence

from llama_index.core.base.base_retriever import BaseRetriever

from pipeline.eval.evaluator import DocumentRetrieverEvaluator
from pipeline.eval.questions import Question
from pipeline.eval.report import Scored

METRICS = ["hit_rate", "recall", "precision", "mrr", "ndcg"]
KS = (5, 10, 20)


def score_retriever(retriever: BaseRetriever, questions: Sequence[Question], ks: Sequence[int] = KS) -> List[Scored]:
    evaluators = {k: DocumentRetrieverEvaluator.from_metric_names(METRICS, retriever=retriever, top_k_docs=k) for k in ks}

    async def score_all() -> List[Scored]:
        scored = []
        for question in questions:
            for k in ks:
                result = await evaluators[k].aevaluate(question.text, expected_ids=list(question.expected_doc_ids))
                scored.append(Scored(question, k, result.metric_vals_dict))
        return scored

    return asyncio.run(score_all())

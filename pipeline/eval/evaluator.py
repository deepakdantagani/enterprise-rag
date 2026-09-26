"""EVAL-1: DocumentRetrieverEvaluator, LlamaIndex's RetrieverEvaluator scored on documents, not chunks.

The benchmark's answer key is documents: qst_0431 (completeness) expects dsid_f6e3b7ad...
"Emergency rollback: Serving Runtime (Hosted + Dedicated)" and dsid_840703a1... "Runtime
release pipeline: rollback procedure". A retriever returns chunks, and a 4,429-char page cut
at 512 tokens is several of them. RetrieverEvaluator scores chunk ids, so it would never match
a dsid, and one page could fill every place in the top k.

This overrides only the hook that lists what was retrieved: each chunk becomes its source
document, a document keeps its best place and its best chunk, and the list is cut at
`top_k_docs`. The metrics (hit_rate, recall, mrr, ndcg) are LlamaIndex's, unchanged.

    >>> from llama_index.core import Document, SummaryIndex
    >>> from llama_index.core.node_parser import SentenceSplitter
    >>> pages = [Document(id_="dsid_a", text="Rollback step one. " * 60), Document(id_="dsid_b", text="Rollback pipeline.")]
    >>> chunks = SentenceSplitter(chunk_size=64, chunk_overlap=0).get_nodes_from_documents(pages)
    >>> len(chunks)
    7
    >>> evaluator = DocumentRetrieverEvaluator.from_metric_names(
    ...     ["recall", "mrr"], retriever=SummaryIndex(chunks).as_retriever(), top_k_docs=10)
    >>> result = evaluator.evaluate("How do I roll back?", expected_ids=["dsid_b"])
    >>> result.retrieved_ids
    ['dsid_a', 'dsid_b']
    >>> result.metric_vals_dict
    {'recall': 1.0, 'mrr': 0.5}
"""
from typing import List, Tuple

from llama_index.core.evaluation import RetrieverEvaluator
from llama_index.core.evaluation.retrieval.base import RetrievalEvalMode
from pydantic import Field


class DocumentRetrieverEvaluator(RetrieverEvaluator):
    """RetrieverEvaluator whose retrieved ids are the first `top_k_docs` distinct source documents."""

    top_k_docs: int = Field(default=10, gt=0, description="How many distinct documents are scored.")

    async def _aget_retrieved_ids_and_texts(
        self, query: str, mode: RetrievalEvalMode = RetrievalEvalMode.TEXT
    ) -> Tuple[List[str], List[str]]:
        chunks = await self.retriever.aretrieve(query)
        for postprocessor in self.node_postprocessors or []:
            chunks = postprocessor.postprocess_nodes(chunks, query_str=query)
        best_chunk_of_document = {}
        for chunk in chunks:
            if chunk.node.ref_doc_id is None:
                raise ValueError(f"chunk {chunk.node.node_id} has no source document to score")
            best_chunk_of_document.setdefault(chunk.node.ref_doc_id, chunk.node.get_content())
        top_documents = list(best_chunk_of_document.items())[: self.top_k_docs]
        return [doc_id for doc_id, _ in top_documents], [text for _, text in top_documents]

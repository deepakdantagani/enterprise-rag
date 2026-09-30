"""GEN-2a: first_documents and document_block, v4's ranked chunks as the documents the answerer reads.

The leaderboard scores answers (GEN-1), and the benchmark's own baseline (BM25 + GPT-5.4, 50.6)
gives its LLM the top 10 whole documents. v4 ranks chunks, and a long document matches in
several places: for qst_0001 ("default size limits for file uploads … multipart upload support
on the OpenAI-compatible API endpoints") the gold document's three chunks rank #1, #2 and #8,
and 14 chunks hold 10 documents. So a document ranks where its best chunk ranks, repeats are
skipped, and the chunk texts are dropped: the answerer reads each whole document (GEN-2b).
All 470 saved questions reach 10 documents, within 11 chunks at the median and 27 at most.

    >>> document_block(1, "dsid_a", "Q3 budget", "Priya approved it.")
    '--- Document 1 (ID: dsid_a) ---\\nTitle: Q3 budget\\n\\nPriya approved it.'
"""
from typing import List, Sequence

from llama_index.core.schema import NodeWithScore

TOP_DOCUMENTS = 10  # as the benchmark's baseline answerer


def first_documents(ranked: Sequence[NodeWithScore], count: int = TOP_DOCUMENTS) -> List[str]:
    """The first `count` distinct documents of ranked chunks, each where its best chunk ranks."""
    return list(dict.fromkeys(chunk.node.ref_doc_id for chunk in ranked))[:count]  # unique, first-seen order


def document_block(number: int, doc_id: str, title: str, content: str) -> str:
    """One document as the benchmark's baseline shows it to its LLM (src/utils/retrieval.py)."""
    return f"--- Document {number} (ID: {doc_id}) ---\nTitle: {title}\n\n{content}"

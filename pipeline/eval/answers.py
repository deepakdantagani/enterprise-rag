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
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Union

from llama_index.core.schema import NodeWithScore

TOP_DOCUMENTS = 10  # as the benchmark's baseline answerer


def first_documents(ranked: Sequence[NodeWithScore], count: int = TOP_DOCUMENTS) -> List[str]:
    """The first `count` distinct documents of ranked chunks, each where its best chunk ranks."""
    return list(dict.fromkeys(chunk.node.ref_doc_id for chunk in ranked))[:count]  # unique, first-seen order


def documents_by_id(parquet_path: Union[str, Path], doc_ids: Sequence[str]) -> Dict[str, Tuple[str, str]]:
    """GEN-2b: title and whole content of each asked document, read in one pass over the corpus.

    The corpus is one 1.4 GB row group, so every read scans it all (1.2 s): ask once for every
    question's documents (4,532 over the 470), not once per question. 4 ids each name two
    different documents (a benchmark data slip): the second text follows the first.
    """
    import pyarrow.parquet as pq
    rows = pq.read_table(parquet_path, columns=["doc_id", "title", "content"],
                         filters=[("doc_id", "in", list(doc_ids))]).to_pylist()
    documents: Dict[str, Tuple[str, str]] = {}
    for row in rows:
        title = (row["title"] or "").strip()
        if row["doc_id"] in documents:
            first_title, first_content = documents[row["doc_id"]]
            documents[row["doc_id"]] = (first_title, f"{first_content}\n\n{title}\n\n{row['content']}")
        else:
            documents[row["doc_id"]] = (title, row["content"] or "")
    return documents


def document_block(number: int, doc_id: str, title: str, content: str) -> str:
    """One document as the benchmark's baseline shows it to its LLM (src/utils/retrieval.py)."""
    return f"--- Document {number} (ID: {doc_id}) ---\nTitle: {title}\n\n{content}"

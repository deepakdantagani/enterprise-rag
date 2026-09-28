"""EVAL-3a: parquet_documents, documents.parquet rows as LlamaIndex Documents, in batches, no cleaning.

The naive baseline reads the benchmark's whole corpus as it ships: data/_full/documents.parquet,
511,962 rows of doc_id, source_type, title, content across all 9 sources, 2.46B chars of
content. That is too much to hold as Documents at once, so rows come in batches.

Each row becomes Document(id_=doc_id): the dsid is the id, so every chunk's ref_doc_id is the
dsid and EVAL-1 can score it. Only `content` is embedded. `title` and `source_type` stay as
metadata for reports but are excluded from the embedded and LLM text: the first sample run
failed on titles that hold a whole body (497 of them, 493 in Slack, the longest 10,693 chars
in dsid_c655aa63...), because SentenceSplitter counts embedded metadata against the 512-token
chunk.

EVAL-3i: document_text, the title merged into the text (`with_title=True`). Excluding the title
from every document fixed 497 but hid the name of the rest: qst_0063 asks for "NorthPoint
Signalworks", a HubSpot record whose title is the only place that name appears, and neither dense
nor BM25 search can match it (4 of the misses at top 100, 2 HubSpot and 2 Slack). As body text a
long title is split like any text, so it cannot overflow a chunk. A body that already starts with
its title (1,697 rows, 1,656 in Slack) and a blank title (15 in Slack)
are left as they are. The baseline stays title-free; `with_title` is opt-in until it is measured.

    >>> document_text("Runbook", "Roll back the release.")
    'Runbook\\n\\nRoll back the release.'

EVAL-3g: a row with blank content is skipped. The full run crashed at batch 279 on the one empty
document in the corpus, dsid_33cbedf0... (Slack, content ''), because Voyage rejects an empty
input. It is no question's expected doc, and there is nothing in it to embed or retrieve.

    >>> import pyarrow as pa, pyarrow.parquet as pq, tempfile, os
    >>> path = os.path.join(tempfile.mkdtemp(), "documents.parquet")
    >>> pq.write_table(pa.Table.from_pylist([{"doc_id": "dsid_a", "source_type": "confluence",
    ...     "title": "Runbook", "content": "Roll back the release."}]), path)
    >>> [document] = next(parquet_documents(path))
    >>> document.id_, document.text, document.metadata
    ('dsid_a', 'Roll back the release.', {'source_type': 'confluence', 'title': 'Runbook'})
"""
from pathlib import Path
from typing import Iterator, List, Optional, Union

import pyarrow.parquet as pq
from llama_index.core import Document

METADATA_KEYS = ["source_type", "title"]  # kept for reports, never embedded


def document_text(title: Optional[str], content: str) -> str:
    """The title, then a blank line, then the content; the content alone if the title adds nothing."""
    title = (title or "").strip()
    if not title or content.lstrip().startswith(title):
        return content
    return f"{title}\n\n{content}"


def parquet_documents(path: Union[str, Path], batch_size: int = 1000, with_title: bool = False) -> Iterator[List[Document]]:
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
        yield [Document(id_=row["doc_id"], text=document_text(row["title"], row["content"]) if with_title else row["content"],
                        metadata={key: row[key] for key in METADATA_KEYS},
                        excluded_embed_metadata_keys=METADATA_KEYS, excluded_llm_metadata_keys=METADATA_KEYS)
               for row in batch.to_pylist() if row["content"].strip()]

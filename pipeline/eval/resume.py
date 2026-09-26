"""EVAL-3d1: embedded_doc_ids, the dsids already in the Qdrant collection, so a re-run skips them.

The full baseline embeds ~1.3M chunks in ~2.5 h. If it stops, the next run should embed only
what is missing. IngestionPipeline's own way (a docstore, EVAL-3b) keeps every document in a
SimpleDocumentStore, which at 511,962 documents is a ~2.5 GB JSON file rewritten after every
batch. Qdrant already holds the answer: each stored chunk's payload carries `ref_doc_id`, its
dsid. So before a run we read those ids once, and the run drops documents already there.

Known gap: QdrantVectorStore uploads a batch's chunks 64 at a time, so a crash in the middle
of an upload can leave one batch's last documents half-written, and they would be skipped. At
most one batch (1,000 of 511,962 documents) is at risk; the run log names the batch in flight.

    >>> from qdrant_client import QdrantClient
    >>> embedded_doc_ids(QdrantClient(":memory:"), "baseline")
    set()
"""
from typing import Set

from qdrant_client import QdrantClient

PAGE_SIZE = 10_000  # points per scroll request


def embedded_doc_ids(client: QdrantClient, collection_name: str, page_size: int = PAGE_SIZE) -> Set[str]:
    if not client.collection_exists(collection_name):
        return set()
    doc_ids, offset = set(), None
    while True:
        points, offset = client.scroll(collection_name, limit=page_size, offset=offset,
                                       with_payload=["ref_doc_id"], with_vectors=False)
        doc_ids.update(point.payload["ref_doc_id"] for point in points)
        if offset is None:
            return doc_ids

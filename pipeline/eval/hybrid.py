"""RET-1: copy_to_hybrid, every v0 chunk into a hybrid collection: its Voyage vector unchanged, plus BM25.

v0 (EVAL-3e) searches by meaning only: one unnamed 1,024-number Voyage vector per chunk in
baseline__voyage_4. Keyword search needs a second, sparse vector per chunk, and LlamaIndex's
hybrid Qdrant store wants both as named vectors (text-dense, text-sparse-new) in one collection.
So the 1,609,717 chunks are copied, not re-embedded: each point comes back as its TextNode with
the stored vector as its embedding, and the hybrid store adds the BM25 vector on the way in.
Cost: no Voyage calls; BM25 is stopwords + a stemmer + a formula, computed locally.

The first runbook chunk (dsid_e54ef48b…) keeps all 1,024 numbers and payload fields and gains
157 BM25 words, led by 'canari' (canary, 11 times, weight 1.986). The model's default average
length of 256 words is kept for v1 (ours measure 195 on 2,000 chunks); tuning it is its own story.

RET-2: sparse_retriever, keyword search alone, to score BM25 with v0's metrics before fusing it.
LlamaIndex's retriever embeds every question even in sparse mode and never uses the vector, so it
gets MockEmbedding instead of Voyage: pure BM25, $0. On qst_0017 ("… tiered uptime SLA
counteroffer for the maritime logistics SaaS customer …") BM25 ranks the expected HubSpot
record first; on qst_0063 "NorthPoint" pulls in a different company's Fireflies meeting instead.

    >>> from qdrant_client.models import Record
    >>> node = node_from_point(Record(id="c1", vector=[0.5, 0.5], payload={
    ...     "_node_content": '{"id_": "c1", "text": "Roll back.", "class_name": "TextNode"}',
    ...     "_node_type": "TextNode", "doc_id": "dsid_a", "document_id": "dsid_a", "ref_doc_id": "dsid_a"}))
    >>> node.node_id, node.text, node.embedding
    ('c1', 'Roll back.', [0.5, 0.5])
"""
from typing import Optional

from llama_index.core import MockEmbedding, VectorStoreIndex
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.utils import metadata_dict_to_node
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import Record

SPARSE_MODEL = "Qdrant/bm25"  # FastEmbed's BM25; LlamaIndex's default sparse model is a SPLADE-style one
RETRIEVED_CHUNKS = 50  # as in v0, so dense and BM25 are compared on the same depth
UNUSED_QUERY_EMBEDDING = MockEmbedding(embed_dim=1024)  # sparse mode never reads the question's dense vector


def hybrid_store(client: QdrantClient, collection_name: str,
                 aclient: Optional[AsyncQdrantClient] = None) -> QdrantVectorStore:
    return QdrantVectorStore(client=client, aclient=aclient, collection_name=collection_name,
                             enable_hybrid=True, fastembed_sparse_model=SPARSE_MODEL)


def node_from_point(point: Record) -> BaseNode:
    node = metadata_dict_to_node(point.payload)
    node.embedding = point.vector
    return node


def copy_to_hybrid(client: QdrantClient, source: str, store: QdrantVectorStore, page_size: int = 1000) -> int:
    """Copy every point of `source` not yet in the store's collection; returns how many were copied."""
    copied, offset = 0, None
    while True:
        points, offset = client.scroll(source, limit=page_size, offset=offset, with_payload=True, with_vectors=True)
        already = ({found.id for found in client.retrieve(store.collection_name, [point.id for point in points])}
                   if client.collection_exists(store.collection_name) else set())
        nodes = [node_from_point(point) for point in points if point.id not in already]
        if nodes:
            store.add(nodes)
        copied += len(nodes)
        if offset is None:
            return copied


def sparse_retriever(store: QdrantVectorStore, top_k: int = RETRIEVED_CHUNKS) -> BaseRetriever:
    index = VectorStoreIndex.from_vector_store(store, embed_model=UNUSED_QUERY_EMBEDDING)
    return index.as_retriever(vector_store_query_mode="sparse", sparse_top_k=top_k, similarity_top_k=top_k)

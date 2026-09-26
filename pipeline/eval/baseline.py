"""EVAL-3b: baseline_pipeline, the naive baseline as one LlamaIndex IngestionPipeline.

The baseline is the plain default: SentenceSplitter (the splitter VectorStoreIndex uses when you
choose none) at 512 tokens with 50 overlap, then the embedder, into the vector store. Every
clean-up story has to beat what this produces. On the real runbook dsid_f6e3b7ad... "Emergency
rollback: Serving Runtime (Hosted + Dedicated)", 993 tokens become 3 chunks of 480, 474 and 53
tokens, each with ref_doc_id = the dsid, which is what EVAL-1 scores.

The full corpus is ~2.5 h of embedding, so a crash must not start over: the docstore keeps a hash
of each document, and a re-run of the same document embeds nothing (DocstoreStrategy.UPSERTS,
IngestionPipeline's default when a docstore and a vector store are given).

    >>> from llama_index.core import Document, MockEmbedding
    >>> from llama_index.core.storage.docstore import SimpleDocumentStore
    >>> from llama_index.core.vector_stores import SimpleVectorStore
    >>> pipeline = baseline_pipeline(MockEmbedding(embed_dim=8), SimpleVectorStore(), SimpleDocumentStore())
    >>> [chunk.ref_doc_id for chunk in pipeline.run(documents=[Document(id_="dsid_b", text="Pin the runtime.")])]
    ['dsid_b']
    >>> pipeline.run(documents=[Document(id_="dsid_b", text="Pin the runtime.")])
    []
"""
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore.types import BaseDocumentStore
from llama_index.core.vector_stores.types import BasePydanticVectorStore

CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50


def baseline_pipeline(embed_model: BaseEmbedding, vector_store: BasePydanticVectorStore,
                      docstore: BaseDocumentStore) -> IngestionPipeline:
    return IngestionPipeline(
        transformations=[SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP), embed_model],
        vector_store=vector_store,
        docstore=docstore,
    )

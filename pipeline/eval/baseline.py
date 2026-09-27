"""EVAL-3b: baseline_pipeline, the naive baseline as one LlamaIndex IngestionPipeline.
EVAL-3d3: ingest_corpus, the corpus through that pipeline batch by batch; `python -m
pipeline.eval.baseline [--sample]` ingests with voyage-4 into Qdrant, then scores every question
(EVAL-3c) with Phoenix tracing, and writes runs/<date>-<collection>/metrics.json.

The baseline is the plain default: SentenceSplitter (the splitter VectorStoreIndex uses when you
choose none) at 512 tokens with 50 overlap, then the embedder, into the vector store. Every
clean-up story has to beat what this produces. On the real runbook dsid_f6e3b7ad... "Emergency
rollback: Serving Runtime (Hosted + Dedicated)", 993 tokens become 3 chunks of 480, 474 and 53
tokens, each with ref_doc_id = the dsid, which is what EVAL-1 scores.

The full corpus is ~2.5 h of embedding, so a stopped run must not start over. It resumes from
what Qdrant already holds (EVAL-3d1, `skip_doc_ids`), not from a docstore: a docstore of 511,962
documents is a ~2.5 GB JSON file. `--sample` runs the same code on EVAL-3d2's 207 documents.

    >>> from llama_index.core import Document, MockEmbedding
    >>> from llama_index.core.storage.docstore import SimpleDocumentStore
    >>> from llama_index.core.vector_stores import SimpleVectorStore
    >>> pipeline = baseline_pipeline(MockEmbedding(embed_dim=8), SimpleVectorStore(), SimpleDocumentStore())
    >>> [chunk.ref_doc_id for chunk in pipeline.run(documents=[Document(id_="dsid_b", text="Pin the runtime.")])]
    ['dsid_b']
    >>> pipeline.run(documents=[Document(id_="dsid_b", text="Pin the runtime.")])
    []
"""
import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import AbstractSet, Optional, Sequence

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore.types import BaseDocumentStore
from llama_index.core.vector_stores.types import BasePydanticVectorStore

from pipeline.eval.documents import parquet_documents
from pipeline.eval.questions import load_questions
from pipeline.eval.report import metrics_report
from pipeline.eval.score import score_retriever
from pipeline.observability import PipelineEvent, StageDone, dispatcher, events_logged_to

CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50
RETRIEVED_CHUNKS = 50  # enough chunks for 20 distinct documents in almost every case
ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = ROOT / "data/_full/documents.parquet"
QUESTIONS = ROOT / "data/_full/questions.jsonl"
QDRANT_URL = "http://localhost:6333"


def baseline_pipeline(embed_model: BaseEmbedding, vector_store: BasePydanticVectorStore,
                      docstore: Optional[BaseDocumentStore] = None) -> IngestionPipeline:
    return IngestionPipeline(
        transformations=[SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP), embed_model],
        vector_store=vector_store,
        docstore=docstore,
    )


def ingest_corpus(documents_path: Path, vector_store: BasePydanticVectorStore, embed_model: BaseEmbedding,
                  skip_doc_ids: AbstractSet[str] = frozenset(), keep_doc_ids: Optional[AbstractSet[str]] = None,
                  batch_size: int = 1000) -> int:
    """Embed every document not in `skip_doc_ids` (and in `keep_doc_ids`, if given); one StageDone per batch."""
    pipeline, embedded = baseline_pipeline(embed_model, vector_store), 0
    for number, batch in enumerate(parquet_documents(documents_path, batch_size=batch_size)):
        to_embed = [document for document in batch if document.id_ not in skip_doc_ids
                    and (keep_doc_ids is None or document.id_ in keep_doc_ids)]
        started = time.monotonic()
        if to_embed:
            pipeline.run(documents=to_embed)
        embedded += len(to_embed)
        dispatcher.event(StageDone(source="all", stage=f"embed batch {number}", files=len(to_embed), failed=0,
                                   seconds=round(time.monotonic() - started, 3)))
    return embedded


def main(argv: Optional[Sequence[str]] = None) -> None:
    import pyarrow.parquet as pq
    import os

    from dotenv import load_dotenv
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient, QdrantClient

    from pipeline.eval.embedders import EMBEDDERS, collection_name, embed_model_named
    from pipeline.eval.resume import embedded_doc_ids
    from pipeline.eval.sample import sample_corpus
    from pipeline.eval.tracing import trace_to_phoenix

    parser = argparse.ArgumentParser(description="Naive baseline: every document, SentenceSplitter(512), voyage-4, Qdrant.")
    parser.add_argument("--sample", action="store_true", help="27 questions, 207 documents from all 9 sources (EVAL-3d2)")
    parser.add_argument("--embed", choices=list(EMBEDDERS), default=next(iter(EMBEDDERS)), help="embedding model (EVAL-3f)")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")  # VOYAGE_API_KEY for the Voyage models
    collection = collection_name(args.embed, args.sample)
    questions, keep_doc_ids = load_questions(QUESTIONS).questions, None
    if args.sample:
        table = pq.read_table(DOCUMENTS, columns=["doc_id", "source_type"])
        questions, keep_doc_ids = sample_corpus(questions, dict(zip(table["doc_id"].to_pylist(), table["source_type"].to_pylist())))
    client = QdrantClient(url=QDRANT_URL)
    vector_store = QdrantVectorStore(client=client, aclient=AsyncQdrantClient(url=QDRANT_URL),  # the evaluator retrieves async
                                     collection_name=collection)
    run_dir = ROOT / "runs" / f"{date.today()}-{collection}"
    trace_to_phoenix(project=collection)
    embed_model = embed_model_named(args.embed, voyage_api_key=os.environ.get("VOYAGE_API_KEY"))
    with events_logged_to(run_dir / "events.jsonl", only=PipelineEvent):
        ingest_corpus(DOCUMENTS, vector_store, embed_model, skip_doc_ids=embedded_doc_ids(client, collection),
                      keep_doc_ids=keep_doc_ids)
    retriever = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model).as_retriever(similarity_top_k=RETRIEVED_CHUNKS)
    rows = metrics_report(score_retriever(retriever, questions))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    config = {"commit": commit, "collection": collection, "embed_model": args.embed, "chunk_size": CHUNK_SIZE,
              "chunk_overlap": CHUNK_OVERLAP, "retrieved_chunks": RETRIEVED_CHUNKS, "questions": len(questions)}
    (run_dir / "metrics.json").write_text(json.dumps({"config": config, "rows": [row._asdict() for row in rows]}, indent=2))
    for row in rows:
        print(f"{row.group:34} k={row.k:<3} n={row.questions:<4}", "  ".join(f"{name}={value:.3f}" for name, value in row.means.items()))


if __name__ == "__main__":
    main()

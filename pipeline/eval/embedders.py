"""EVAL-3f: embed_model_named and collection_name, the embedder the baseline runs on: voyage-4.

The local qwen3-embedding:0.6b on Ollama was tried first and removed: it ran at ~22 chunks/s on
this Mac (GPU ~95% busy, the same through Ollama and PyTorch on MPS, at any batch size), so the
full corpus of ~1.56M chunks was ~20 h. voyage-4 runs on Voyage's servers at 126 chunks/s one
request at a time (~3.4 h), and on the --sample corpus (207 documents, 27 questions) it scored
recall@10 1.000 against 0.963 for the local model. A new embedder is a new row in EMBEDDERS.

Each embedder gets its own Qdrant collection: vectors from two models are not comparable, and a
question must be embedded by the same model as the chunks it searches.

    >>> collection_name("voyage-4", sample=True)
    'baseline_sample__voyage_4'
"""
import re
from typing import Optional

from llama_index.core.base.embeddings.base import BaseEmbedding

EMBEDDERS = {  # name -> where it runs; the first is the default
    "voyage-4": "voyage",  # Voyage API, $0.06 per 1M tokens (Sep 2026), 1,024 dimensions
}
DIMENSIONS = 1024
VOYAGE_BATCH = 128  # texts per request: 128 chunks x ~512 tokens is ~65K tokens


def embed_model_named(name: str, voyage_api_key: Optional[str] = None) -> BaseEmbedding:
    if name not in EMBEDDERS:
        raise ValueError(f"unknown embedder {name!r}; known: {', '.join(EMBEDDERS)}")
    from llama_index.embeddings.voyageai import VoyageEmbedding
    return VoyageEmbedding(model_name=name, voyage_api_key=voyage_api_key, output_dimension=DIMENSIONS,
                           embed_batch_size=VOYAGE_BATCH)


def collection_name(embedder: str, sample: bool) -> str:
    corpus = "baseline_sample" if sample else "baseline"
    return f"{corpus}__{re.sub(r'[^a-z0-9]+', '_', embedder.lower())}"

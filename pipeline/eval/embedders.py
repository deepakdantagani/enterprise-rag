"""EVAL-3f: embed_model_named and collection_name, one baseline command for each embedder.

Local qwen3-embedding:0.6b on Ollama runs at ~22 chunks/s on this Mac (measured: GPU ~95% busy,
the same speed through Ollama and through PyTorch on MPS, at any batch size), so the full
corpus of ~1.56M chunks is ~20 h. An API model moves the work off the laptop. Before choosing,
the --sample corpus (207 documents, 27 questions) is scored with each, so the choice rests on
our own questions, not on public leaderboards.

Each embedder gets its own Qdrant collection: vectors from two models are not comparable, and a
question must be embedded by the same model as the chunks it searches.

    >>> collection_name("voyage-4", sample=True)
    'baseline_sample__voyage_4'
"""
import re
from typing import Optional

from llama_index.core.base.embeddings.base import BaseEmbedding

EMBEDDERS = {  # name -> where it runs; the first is the default
    "qwen3-embedding:0.6b": "ollama",  # local, free, 1,024 dimensions
    "voyage-4": "voyage",  # Voyage API, $0.06 per 1M tokens (Sep 2026), 1,024 dimensions
}
DIMENSIONS = 1024
OLLAMA_BATCH = 32  # batching does not speed Ollama up (measured), 32 keeps requests small
VOYAGE_BATCH = 128  # texts per request: 128 chunks x ~512 tokens is ~65K tokens


def embed_model_named(name: str, voyage_api_key: Optional[str] = None) -> BaseEmbedding:
    if name not in EMBEDDERS:
        raise ValueError(f"unknown embedder {name!r}; known: {', '.join(EMBEDDERS)}")
    if EMBEDDERS[name] == "ollama":
        from llama_index.embeddings.ollama import OllamaEmbedding
        return OllamaEmbedding(model_name=name, embed_batch_size=OLLAMA_BATCH)
    from llama_index.embeddings.voyageai import VoyageEmbedding
    return VoyageEmbedding(model_name=name, voyage_api_key=voyage_api_key, output_dimension=DIMENSIONS,
                           embed_batch_size=VOYAGE_BATCH)


def collection_name(embedder: str, sample: bool) -> str:
    corpus = "baseline_sample" if sample else "baseline"
    return f"{corpus}__{re.sub(r'[^a-z0-9]+', '_', embedder.lower())}"

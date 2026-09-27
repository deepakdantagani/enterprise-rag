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

RET-3a: saved_query_embeddings, so a re-score reuses the question vectors instead of paying Voyage
again. The scorer retrieves each of the 470 questions once per k (5, 10, 20), and LlamaIndex's
retriever embeds the question every time: 1,410 Voyage calls per run (~$0.0045), and RET-3 ran
three. The 470 vectors were embedded once (input_type "query", 95 s) into
data/_index/question_embeddings/voyage-4.jsonl; a question not in the file goes to the fallback.

    >>> model = SavedQueryEmbedding(saved={"Who approved the Q3 budget?": [0.1, 0.2]})
    >>> model.get_query_embedding("Who approved the Q3 budget?")
    [0.1, 0.2]
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr

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


class SavedQueryEmbedding(BaseEmbedding):
    """A question's saved vector when there is one, else the fallback embedder's (e.g. Voyage)."""
    fallback: Optional[BaseEmbedding] = None
    _saved: Dict[str, List[float]] = PrivateAttr()

    def __init__(self, saved: Dict[str, List[float]], fallback: Optional[BaseEmbedding] = None) -> None:
        super().__init__(model_name="saved-query-embeddings", fallback=fallback)
        self._saved = saved

    @property
    def saved_count(self) -> int:
        return len(self._saved)

    def _get_query_embedding(self, query: str) -> List[float]:
        if query in self._saved:
            return self._saved[query]
        if self.fallback is None:
            raise KeyError(f"no saved embedding and no fallback for {query!r}")
        return self.fallback.get_query_embedding(query)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        if query in self._saved or self.fallback is None:
            return self._get_query_embedding(query)
        return await self.fallback.aget_query_embedding(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        raise NotImplementedError("saved embeddings are for questions; chunks are embedded by the real model")


def saved_query_embeddings(path: Union[str, Path], fallback: Optional[BaseEmbedding] = None) -> SavedQueryEmbedding:
    rows = (json.loads(line) for line in Path(path).read_text().splitlines())
    return SavedQueryEmbedding(saved={row["text"]: row["embedding"] for row in rows}, fallback=fallback)

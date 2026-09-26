"""SLACK-11a: embed_model(), the embedding model every Slack thread goes through.

Qwen3-Embedding-0.6B, run locally by Ollama, called through LlamaIndex's own `OllamaEmbedding`:
no wrapper of ours. Chosen from 20 models (2026-09-26): it fits a whole thread (window 32,768;
the largest thread is 4,470 of its tokens), has the best comparable retrieval of the small open
models (MTEB English v2 Retrieval 61.8), keeps the data on the laptop, costs nothing per run,
and is Apache-2.0. 1,024 numbers per vector: 1.17 GB of float32 for the 285,597 threads.

`num_ctx` is set explicitly: Ollama cuts anything past it without an error (the largest thread
forced to 2,048 came back cut to 2,047 tokens, its vector still 0.94 similar, so nothing looks
wrong), and its default can change between versions. EmbeddingWindowGuard (SLACK-10) is the check.

Threads are embedded as they are. Questions need Qwen's instruction line; SLACK-11c sets it.

Measured on this Mac (M5 Pro): about 10.5 threads a second, so a full run is about 7.7 hours.

Swappable, as a production setting should be: the rest of the pipeline only sees LlamaIndex's
`BaseEmbedding`. `EMBED_PROVIDER` picks a row of PROVIDERS; adding a provider (OpenAI, Voyage,
Hugging Face, ...) is one builder + one row + its `llama-index-embeddings-*` package, imported only
when chosen. The settings are environment variables (see .env.example) read when called, never at
import; unset, they are Qwen3-Embedding-0.6B on the local Ollama. API keys never pass through
here: each provider's own package reads its own variable (OPENAI_API_KEY, ...).
"""
import os
from typing import Callable, Dict, Mapping, NamedTuple, Optional

from llama_index.core.base.embeddings.base import BaseEmbedding


class EmbedSettings(NamedTuple):
    provider: str     # a key of PROVIDERS
    model: str        # the provider's model name
    base_url: str     # where the provider listens (Ollama, or any self-hosted server)
    window: int       # the model's context length; Ollama gets it as num_ctx, the guard should match
    dimensions: int   # numbers per vector; the Qdrant collection is created with this size (SLACK-11b)


# Each environment variable and its default. The model, window and dimensions belong together:
# change them together.
DEFAULTS = {
    "EMBED_PROVIDER": "ollama",
    "EMBED_MODEL": "qwen3-embedding:0.6b",
    "EMBED_BASE_URL": "http://localhost:11434",
    "EMBED_WINDOW": "32768",
    "EMBED_DIMENSIONS": "1024",
}


def ollama(settings: EmbedSettings) -> BaseEmbedding:
    """Ollama, told to read up to the model's full window: it cuts past num_ctx without an error."""
    from llama_index.embeddings.ollama import OllamaEmbedding  # imported only when chosen

    return OllamaEmbedding(model_name=settings.model, base_url=settings.base_url,
                           ollama_additional_kwargs={"num_ctx": settings.window})


PROVIDERS: Dict[str, Callable[[EmbedSettings], BaseEmbedding]] = {
    "ollama": ollama,
}


def embed_settings(environ: Mapping[str, str] = os.environ) -> EmbedSettings:
    """The embedding settings from the environment, each falling back to its default; checked here,
    so a bad value stops the run before any thread is read.

    >>> embed_settings({"EMBED_MODEL": "bge-m3", "EMBED_WINDOW": "8192"})
    EmbedSettings(provider='ollama', model='bge-m3', base_url='http://localhost:11434', window=8192, dimensions=1024)
    """
    value = {name: environ.get(name, default) for name, default in DEFAULTS.items()}
    if value["EMBED_PROVIDER"] not in PROVIDERS:
        raise ValueError(f"EMBED_PROVIDER {value['EMBED_PROVIDER']!r} is not one of {sorted(PROVIDERS)}")
    return EmbedSettings(value["EMBED_PROVIDER"], value["EMBED_MODEL"], value["EMBED_BASE_URL"],
                         positive_int("EMBED_WINDOW", value["EMBED_WINDOW"]),
                         positive_int("EMBED_DIMENSIONS", value["EMBED_DIMENSIONS"]))


def positive_int(name: str, text: str) -> int:
    number = int(text) if text.strip().isdigit() else 0
    if number <= 0:
        raise ValueError(f"{name} must be a positive whole number, got {text!r}")
    return number


def embed_model(settings: Optional[EmbedSettings] = None) -> BaseEmbedding:
    """The embedding model for Slack threads, built by the provider the settings name."""
    settings = settings or embed_settings()
    return PROVIDERS[settings.provider](settings)

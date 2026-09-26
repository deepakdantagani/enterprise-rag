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
when chosen. LlamaIndex's own `resolve_embed_model` / `Settings.embed_model` take "default" (OpenAI),
"local:..." (Hugging Face) or "clip...", with no Ollama form, so they cannot select this model.

The settings are environment variables, read when called (never at import): a real variable wins,
then the repository's `.env` (see .env.example), then the defaults below. API keys never pass
through here: each provider's package reads its own variable (OPENAI_API_KEY, ...).

Every setting that depends on the model is tied to it: Ollama's num_ctx is the window, the guard's
ceiling is the window less a margin for the tokenizer (`window_guard`), and the vector size is
checked against a real vector before anything is stored (`check_dimensions`).
"""
import os
from pathlib import Path
from typing import Callable, Dict, Mapping, NamedTuple, Optional

from dotenv import load_dotenv
from llama_index.core.base.embeddings.base import BaseEmbedding

from pipeline.slack.window import EmbeddingWindowGuard

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
OLLAMA_URL = "http://localhost:11434"  # Ollama's own default, used when EMBED_BASE_URL is empty
TOKENIZER_MARGIN = 0.8  # the guard counts with cl100k; Qwen counts +4.4% (1,000 real threads), BERT-style more


class EmbedSettings(NamedTuple):
    provider: str     # a key of PROVIDERS
    model: str        # the provider's model name
    base_url: str     # where the provider listens; empty = the provider's own default
    window: int       # the model's context length: Ollama's num_ctx and the guard's ceiling come from it
    dimensions: int   # numbers per vector; the Qdrant collection is created with this size (SLACK-11b)


# Each environment variable and its default. The model, window and dimensions belong together:
# change them together.
DEFAULTS = {
    "EMBED_PROVIDER": "ollama",
    "EMBED_MODEL": "qwen3-embedding:0.6b",
    "EMBED_BASE_URL": "",
    "EMBED_WINDOW": "32768",
    "EMBED_DIMENSIONS": "1024",
}


def ollama(settings: EmbedSettings) -> BaseEmbedding:
    """Ollama, told to read up to the model's full window: it cuts past num_ctx without an error."""
    from llama_index.embeddings.ollama import OllamaEmbedding  # imported only when chosen

    return OllamaEmbedding(model_name=settings.model, base_url=settings.base_url or OLLAMA_URL,
                           ollama_additional_kwargs={"num_ctx": settings.window})


PROVIDERS: Dict[str, Callable[[EmbedSettings], BaseEmbedding]] = {
    "ollama": ollama,
}


def embed_settings(environ: Optional[Mapping[str, str]] = None) -> EmbedSettings:
    """The embedding settings, each falling back to its default; checked here, so a bad value stops
    the run before any thread is read. With no mapping given: the environment, then `.env`.

    >>> embed_settings({"EMBED_MODEL": "bge-m3", "EMBED_WINDOW": "8192"})
    EmbedSettings(provider='ollama', model='bge-m3', base_url='', window=8192, dimensions=1024)
    """
    if environ is None:
        load_dotenv(ENV_FILE, override=False)  # a variable already set wins over the file
        environ = os.environ
    value = {name: environ.get(name, default) for name, default in DEFAULTS.items()}
    provider(value["EMBED_PROVIDER"])
    return EmbedSettings(value["EMBED_PROVIDER"], value["EMBED_MODEL"], value["EMBED_BASE_URL"],
                         positive_int("EMBED_WINDOW", value["EMBED_WINDOW"]),
                         positive_int("EMBED_DIMENSIONS", value["EMBED_DIMENSIONS"]))


def provider(name: str) -> Callable[[EmbedSettings], BaseEmbedding]:
    if name not in PROVIDERS:
        raise ValueError(f"EMBED_PROVIDER {name!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[name]


def positive_int(name: str, text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        number = 0
    if number <= 0:
        raise ValueError(f"{name} must be a positive whole number, got {text!r}")
    return number


def embed_model(settings: Optional[EmbedSettings] = None) -> BaseEmbedding:
    """The embedding model for Slack threads, built by the provider the settings name."""
    settings = settings or embed_settings()
    return provider(settings.provider)(settings)


def window_guard(settings: EmbedSettings) -> EmbeddingWindowGuard:
    """SLACK-10's guard with its ceiling taken from this model's window, so a smaller model makes
    the run stop instead of truncating: 32,768 -> 26,214 (the largest thread is 4,143); 512 -> 409."""
    return EmbeddingWindowGuard(max_tokens=int(settings.window * TOKENIZER_MARGIN))


def check_dimensions(model: BaseEmbedding, settings: EmbedSettings) -> None:
    """Stop before anything is stored if the model's vectors are not EMBED_DIMENSIONS long (the
    Qdrant collection is created with that size)."""
    returned = len(model.get_text_embedding("dimension check"))
    if returned != settings.dimensions:
        raise ValueError(f"EMBED_DIMENSIONS is {settings.dimensions} but {settings.model} returns {returned}")

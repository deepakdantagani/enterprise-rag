"""EVAL-4: trace_to_phoenix, every LlamaIndex call of an eval run becomes a span Phoenix can show.

The report (EVAL-2b) says recall is low for a group; it cannot say why. For that we need to
open one question, say qst_0431 "emergency rollback of a Serving Runtime release", and see the
chunks the retriever returned, their scores, and which documents they came from. Arize Phoenix
shows exactly that, locally, from OpenInference spans.

No code of ours emits spans: OpenInference's LlamaIndexInstrumentor hooks LlamaIndex's own
instrumentation dispatcher (the one pipeline/observability.py already listens to), so every
retrieve, embed and evaluate call is traced as it is. This function only picks where spans go:
the local Phoenix server by default, or a given provider (the tests pass an in-memory one).

Start the UI first, then open http://localhost:6006:

    uv run --with arize-phoenix phoenix serve

    >>> from opentelemetry.sdk.trace import TracerProvider
    >>> provider = TracerProvider()
    >>> trace_to_phoenix(tracer_provider=provider) is provider
    True
"""
from typing import Optional

from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from opentelemetry.sdk.trace import TracerProvider

PHOENIX_PROJECT = "enterprise-rag-eval"


def trace_to_phoenix(project: str = PHOENIX_PROJECT, tracer_provider: Optional[TracerProvider] = None) -> TracerProvider:
    if tracer_provider is None:
        from phoenix.otel import register  # only when sending to a running Phoenix server
        tracer_provider = register(project_name=project, batch=True)
    LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
    return tracer_provider

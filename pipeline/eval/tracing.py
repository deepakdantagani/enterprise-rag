"""EVAL-4: trace_to_phoenix, every LlamaIndex call of an eval run becomes a span Phoenix can show.

The report (EVAL-2b) says recall is low for a group; it cannot say why. For that we need to
open one question, say qst_0431 "emergency rollback of a Serving Runtime release", and see the
chunks the retriever returned, their scores, and which documents they came from. Arize Phoenix
shows exactly that, locally, from OpenInference spans.

No code of ours emits spans: OpenInference's LlamaIndexInstrumentor hooks LlamaIndex's own
instrumentation dispatcher (the one pipeline/observability.py already listens to), so every
retrieve, embed and evaluate call is traced as it is. This function only picks where spans go:
the local Phoenix server by default, or a given provider (the tests pass an in-memory one).

Two settings from the first sample run (207 docs, 822 chunks): embedding vectors are left out of
the spans, because 1,024 numbers per chunk pushed one export batch to 12 MB; and spans go over
HTTP, because Phoenix's gRPC receiver rejects any message over 4 MB.

The provider is plain OpenTelemetry, not phoenix.otel.register: register(protocol="http/protobuf")
in arize-phoenix-otel 0.17.1 raises AttributeError on the HTTP exporter's `_headers`, which
opentelemetry-exporter-otlp-proto-http 1.45 no longer has. The first real run stopped on it.

Start the UI first, then open http://localhost:6006:

    uv run --with arize-phoenix phoenix serve

    >>> from opentelemetry.sdk.trace import TracerProvider
    >>> provider = TracerProvider()
    >>> trace_to_phoenix(tracer_provider=provider) is provider
    True
"""
from typing import Optional

from openinference.instrumentation import TraceConfig
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from openinference.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

PHOENIX_PROJECT = "enterprise-rag-eval"
PHOENIX_TRACES = "http://localhost:6006/v1/traces"  # Phoenix's OTLP-over-HTTP receiver


def trace_to_phoenix(project: str = PHOENIX_PROJECT, tracer_provider: Optional[TracerProvider] = None) -> TracerProvider:
    if tracer_provider is None:
        tracer_provider = TracerProvider(resource=Resource({ResourceAttributes.PROJECT_NAME: project}))
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=PHOENIX_TRACES)))
    LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider, config=TraceConfig(hide_embeddings_vectors=True))
    return tracer_provider

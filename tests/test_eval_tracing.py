"""EVAL-4: trace_to_phoenix, every LlamaIndex call of an eval run becomes a span Phoenix can show.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.core import Document, MockEmbedding, SummaryIndex, VectorStoreIndex
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import tracing as tracing_module  # noqa: E402
from pipeline.eval.evaluator import DocumentRetrieverEvaluator  # noqa: E402
from pipeline.eval.tracing import trace_to_phoenix  # noqa: E402


class TraceToPhoenix(unittest.TestCase):
    def setUp(self):
        self.spans = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.spans))
        trace_to_phoenix(tracer_provider=provider)

    def tearDown(self):
        LlamaIndexInstrumentor().uninstrument()

    def evaluate(self):
        pages = [Document(id_="dsid_a", text="Emergency rollback steps."), Document(id_="dsid_b", text="Release pipeline.")]
        retriever = SummaryIndex.from_documents(pages).as_retriever()
        DocumentRetrieverEvaluator.from_metric_names(["recall"], retriever=retriever).evaluate(
            "How do I roll back?", expected_ids=["dsid_b"])

    def test_a_retrieval_is_a_span(self):
        self.evaluate()
        self.assertIn("RETRIEVER", [span.attributes.get("openinference.span.kind") for span in self.spans.get_finished_spans()])

    def test_the_span_holds_the_question_and_the_retrieved_chunks(self):
        self.evaluate()
        retrieval = next(span for span in self.spans.get_finished_spans()  # the inner retriever span carries the chunks
                         if "retrieval.documents.0.document.content" in span.attributes)
        self.assertIn("How do I roll back?", retrieval.attributes["input.value"])
        self.assertEqual(retrieval.attributes["retrieval.documents.1.document.content"], "Release pipeline.")

    def test_embedding_spans_carry_no_vectors(self):
        # a 1,024-number vector per chunk pushed one batch to 12 MB, over Phoenix's 4 MB limit (sample run)
        index = VectorStoreIndex.from_documents([Document(id_="dsid_a", text="Emergency rollback steps.")],
                                                embed_model=MockEmbedding(embed_dim=8))
        index.as_retriever().retrieve("How do I roll back?")
        vectors = [value for span in self.spans.get_finished_spans()
                   for key, value in span.attributes.items() if key.endswith(".embedding.vector")]
        self.assertTrue(vectors)
        self.assertEqual(set(vectors), {"__REDACTED__"})

    def test_by_default_spans_go_to_phoenix_over_http_under_the_project_name(self):
        # the first real run failed here: phoenix.otel.register(protocol="http/protobuf") raised
        # AttributeError on the exporter's missing `_headers`; no test had taken this path
        LlamaIndexInstrumentor().uninstrument()
        provider = trace_to_phoenix(project="baseline_sample")
        [processor] = provider._active_span_processor._span_processors
        self.assertEqual(provider.resource.attributes["openinference.project.name"], "baseline_sample")
        self.assertEqual(processor.span_exporter._endpoint, "http://localhost:6006/v1/traces")

    def test_doctests(self):
        LlamaIndexInstrumentor().uninstrument()  # the doctest instruments on its own
        self.assertEqual(doctest.testmod(tracing_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

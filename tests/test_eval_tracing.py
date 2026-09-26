"""EVAL-4: trace_to_phoenix, every LlamaIndex call of an eval run becomes a span Phoenix can show.

Run: uv run python -m unittest discover tests
"""
import doctest
import sys
import unittest
from pathlib import Path

from llama_index.core import Document, SummaryIndex
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

    def test_doctests(self):
        LlamaIndexInstrumentor().uninstrument()  # the doctest instruments on its own
        self.assertEqual(doctest.testmod(tracing_module).failed, 0)


if __name__ == "__main__":
    unittest.main()

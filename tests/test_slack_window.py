"""SLACK-10: EmbeddingWindowGuard, a pass-through LlamaIndex TransformComponent that stops the run
when a node is over the embedding model's window.

Run: uv run python -m unittest discover tests
"""
import doctest
import pickle
import sys
import unittest
from collections import Counter
from pathlib import Path

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.ingestion.pipeline import get_transformation_hash
from llama_index.core.schema import Document, TextNode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import window as window_module  # noqa: E402
from pipeline.slack.documents import thread_documents  # noqa: E402
from pipeline.slack.nodes import SlackThreadParser  # noqa: E402
from pipeline.slack.thread import id_and_slug  # noqa: E402
from pipeline.slack.window import EmbeddingWindowGuard  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
FIXTURES = ROOT / "tests/fixtures/slack_truth"
PIN_THREAD = "dsid_47db1d5b12a44a9885495cde5305c45d__1725550001-pin-extension-sow-thread.txt"
OTHER_THREAD = "dsid_5badc87efd7a49128d67b0234f809fa1__2987654321.txt"
TEXT = "eng\n\nana: one two three\nben: four five six\n"
# With a word-count tokenizer the embedded text is "channel: eng\nparticipants: ana, ben\n\n"
# (5 words) plus the messages (8 words): 13 words.


def words(text: str) -> list:
    return text.split()


def thread_node(file_name: str = PIN_THREAD, text: str = TEXT) -> TextNode:
    document = Document(id_=id_and_slug(file_name)[0], text=text, metadata={"file_name": file_name})
    [node] = SlackThreadParser().get_nodes_from_documents([document])
    return node


class GuardTheWindow(unittest.TestCase):
    def test_nodes_that_fit_come_back_as_the_same_objects_in_order(self):
        nodes = [thread_node(), thread_node(OTHER_THREAD)]
        returned = EmbeddingWindowGuard(max_tokens=13, tokenizer=words)(nodes)
        self.assertEqual([id(node) for node in returned], [id(node) for node in nodes])

    def test_a_node_over_the_window_stops_the_run_and_every_one_is_named(self):
        nodes = [thread_node(), thread_node(OTHER_THREAD)]
        with self.assertRaises(ValueError) as raised:
            EmbeddingWindowGuard(max_tokens=12, tokenizer=words)(nodes)
        message = str(raised.exception)
        self.assertIn("2 nodes", message)
        self.assertIn("47db1d5b12a44a9885495cde5305c45d (13 tokens)", message)
        self.assertIn("5badc87efd7a49128d67b0234f809fa1 (13 tokens)", message)

    def test_the_size_counts_the_embedded_metadata_lines_not_only_the_text(self):
        node = thread_node()
        self.assertEqual(len(words(node.text)), 8)
        self.assertEqual(EmbeddingWindowGuard(tokenizer=words).embedded_tokens(node), 13)

    def test_too_long_lists_each_node_over_the_window_with_its_size(self):
        guard = EmbeddingWindowGuard(max_tokens=12, tokenizer=words)
        self.assertEqual(guard.too_long([thread_node()]), [("47db1d5b12a44a9885495cde5305c45d", 13)])
        self.assertEqual(EmbeddingWindowGuard(max_tokens=13, tokenizer=words).too_long([thread_node()]), [])

    def test_defaults_are_an_8k_window_and_llamaindex_s_tokenizer(self):
        guard = EmbeddingWindowGuard()
        self.assertEqual(guard.max_tokens, 8192)
        self.assertEqual(guard.embedded_tokens(thread_node()), 21)  # tiktoken cl100k_base, measured
        self.assertEqual(EmbeddingWindowGuard.class_name(), "EmbeddingWindowGuard")

    def test_the_window_is_in_the_cache_key(self):
        nodes = [thread_node()]
        self.assertNotEqual(get_transformation_hash(nodes, EmbeddingWindowGuard()),
                            get_transformation_hash(nodes, EmbeddingWindowGuard(max_tokens=2048)))

    def test_the_tokenizer_survives_pickling_for_parallel_workers(self):
        guard = pickle.loads(pickle.dumps(EmbeddingWindowGuard(max_tokens=12, tokenizer=words)))
        self.assertEqual(guard.embedded_tokens(thread_node()), 13)

    def test_a_window_of_zero_or_less_is_refused(self):
        with self.assertRaises(ValueError):
            EmbeddingWindowGuard(max_tokens=0)

    def test_it_runs_between_the_parser_and_the_embed_model_in_the_pipeline(self):
        documents = list(thread_documents(FIXTURES))
        pipeline = IngestionPipeline(transformations=[SlackThreadParser(), EmbeddingWindowGuard()])
        self.assertEqual(len(pipeline.run(documents=documents)), 50)
        small = IngestionPipeline(transformations=[SlackThreadParser(), EmbeddingWindowGuard(max_tokens=100)])
        with self.assertRaisesRegex(ValueError, "over the embedding window of 100 tokens"):
            small.run(documents=documents)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(window_module).failed, 0)


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_every_thread_fits_an_8k_window_and_697_are_over_2048(self):
        guard, parser, totals, largest = EmbeddingWindowGuard(), SlackThreadParser(), Counter(), 0
        for document in thread_documents(CLEAN):
            for node in parser.get_nodes_from_documents([document]):
                tokens = guard.embedded_tokens(node)
                largest = max(largest, tokens)
                totals["nodes"] += 1
                for window in (512, 1024, 2048, 4096, 8192):
                    totals[f"over_{window}"] += tokens > window
        self.assertEqual(totals, {"nodes": 285_597, "over_512": 253_575, "over_1024": 75_198,
                                  "over_2048": 697, "over_4096": 2, "over_8192": 0})
        self.assertEqual(largest, 4_143)


if __name__ == "__main__":
    unittest.main()

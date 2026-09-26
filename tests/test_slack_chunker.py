"""SLACK-10: SlackMessageChunker, a LlamaIndex NodeParser: a node over the token ceiling -> nodes cut
between messages.

Run: uv run python -m unittest discover tests
"""
import doctest
import pickle
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.ingestion.pipeline import get_transformation_hash
from llama_index.core.schema import Document, MetadataMode, NodeRelationship, TextNode
from llama_index.core.utils import get_tokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import chunker as chunker_module  # noqa: E402
from pipeline.slack.chunker import SlackMessageChunker  # noqa: E402
from pipeline.slack.documents import thread_documents  # noqa: E402
from pipeline.slack.nodes import SlackThreadParser, node_id  # noqa: E402
from pipeline.slack.thread import id_and_slug  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
FIXTURES = ROOT / "tests/fixtures/slack_chunker"      # the smallest real thread over 2,048 tokens
TRUTH_FIXTURES = ROOT / "tests/fixtures/slack_truth"  # NovaCare is here
OVER_BUDGET_ID = "19189bd1792545dfb056da417ec6befa"
NOVACARE_ID = "a4e702bd03254699b0e7bed0000972ab"
SMALL_THREAD = "dsid_47db1d5b12a44a9885495cde5305c45d__1725550001-pin-extension-sow-thread.txt"
SMALL_TEXT = ("eng\n\nana: one two three\nben: four five six\n"
              "ana: seven eight\ncai: nine ten eleven twelve\n")
# With a word-count tokenizer the embedded prefix "channel: eng\nparticipants: ana, ben, cai" is
# 6 words, and the messages are 4, 4, 3 and 5 words: 22 in all.


def words(text: str) -> list:
    return text.split()


def thread_node(file_name: str = SMALL_THREAD, text: str = SMALL_TEXT) -> TextNode:
    document = Document(id_=id_and_slug(file_name)[0], text=text, metadata={"file_name": file_name})
    [node] = SlackThreadParser().get_nodes_from_documents([document])
    return node


def chunk(nodes, max_tokens: int, tokenizer=words):
    return SlackMessageChunker(max_tokens=max_tokens, tokenizer=tokenizer).get_nodes_from_documents(nodes)


def fixture_nodes(folder: Path) -> list:
    return SlackThreadParser().get_nodes_from_documents(list(thread_documents(folder)))


class SplitBetweenMessages(unittest.TestCase):
    def test_a_node_under_the_ceiling_passes_through_as_the_same_object(self):
        node = thread_node()
        self.assertIs(chunk([node], max_tokens=22)[0], node)

    def test_a_node_over_the_ceiling_splits_between_messages_into_equal_halves(self):
        pieces = chunk([thread_node()], max_tokens=16)
        self.assertEqual([piece.text for piece in pieces],
                         ["ana: one two three\nben: four five six\n", "ana: seven eight\ncai: nine ten eleven twelve\n"])
        self.assertEqual([(piece.metadata["first_turn"], piece.metadata["last_turn"]) for piece in pieces],
                         [(0, 1), (2, 3)])

    def test_every_piece_is_at_or_under_the_ceiling_counting_what_the_embedder_sees(self):
        for piece in chunk([thread_node()], max_tokens=16):
            self.assertLessEqual(len(words(piece.get_content(MetadataMode.EMBED))), 16)

    def test_the_pieces_joined_give_back_the_node_text(self):
        node = thread_node()
        for ceiling in (11, 12, 16):  # 11: one message per piece
            self.assertEqual("".join(piece.text for piece in chunk([node], max_tokens=ceiling)), node.text)

    def test_each_piece_keeps_the_threads_fields_and_its_own_turns_and_id(self):
        node = thread_node()
        first, second = chunk([node], max_tokens=16)
        self.assertEqual(second.metadata, {**node.metadata, "first_turn": 2, "last_turn": 3})
        self.assertEqual(second.metadata["participants"], "ana, ben, cai")  # the thread's, not the piece's
        self.assertEqual(second.id_, node_id("47db1d5b12a44a9885495cde5305c45d", 2, 3))
        self.assertEqual(second.excluded_embed_metadata_keys, node.excluded_embed_metadata_keys)
        self.assertEqual(second.excluded_llm_metadata_keys, node.excluded_llm_metadata_keys)

    def test_each_piece_links_to_the_thread_document_and_points_into_its_text(self):
        document_text = SMALL_TEXT
        for piece in chunk([thread_node()], max_tokens=16):
            self.assertEqual(piece.ref_doc_id, "47db1d5b12a44a9885495cde5305c45d")
            self.assertEqual(piece.relationships[NodeRelationship.SOURCE].node_type.name, "DOCUMENT")
            self.assertEqual(document_text[piece.start_char_idx:piece.end_char_idx], piece.text)
            self.assertNotIn(NodeRelationship.NEXT, piece.relationships)

    def test_text_before_the_first_message_goes_with_the_first_message(self):
        node = thread_node(text="eng\n\nsummary\n" + SMALL_TEXT.removeprefix("eng\n\n"))
        first, _ = chunk([node], max_tokens=17)
        self.assertTrue(first.text.startswith("summary\nana: one two three\n"))

    def test_chunking_twice_changes_nothing(self):
        once = chunk([thread_node()], max_tokens=16)
        twice = chunk(once, max_tokens=16)
        self.assertEqual([piece.id_ for piece in twice], [piece.id_ for piece in once])
        self.assertIs(twice[0], once[0])

    def test_a_single_message_over_the_ceiling_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "longer than the ceiling"):
            chunk([thread_node()], max_tokens=10)

    def test_a_node_whose_messages_no_longer_match_its_turns_is_an_error(self):
        node = thread_node()
        node.metadata["last_turn"] = 5
        with self.assertRaisesRegex(ValueError, "turns"):
            chunk([node], max_tokens=16)

    def test_the_fewest_pieces_that_fit_even_past_two(self):
        # messages of 2, 8, 5, 2, 1, 5 and 1 words under the 2-word prefix "channel: eng": 4 pieces fit
        # a ceiling of 10 ([2] [8] [5 2 1] [5 1]); walking forward toward an equal share needs 5.
        text = "eng\n\n" + "".join(f"s{turn}:{' w' * (size - 1)}\n" for turn, size in enumerate([2, 8, 5, 2, 1, 5, 1]))
        node = thread_node(text=text)
        node.metadata = {key: value for key, value in node.metadata.items() if key != "participants"}
        pieces = chunk([node], max_tokens=10)
        self.assertEqual(len(pieces), 4)
        self.assertEqual("".join(piece.text for piece in pieces), node.text)

    def test_a_piece_cannot_be_chunked_again_to_a_lower_ceiling(self):
        # `maria gonzalez:` counts as a speaker only when the name opens 2 lines; inside one piece it
        # opens 1, so the piece no longer re-splits into its turns (32 of 6,770 real pieces at 512)
        text = "eng\n\nmaria gonzalez: a b c\nben: d e f\nmaria gonzalez: g h\nben: i j\n"
        first, _ = chunk([thread_node(text=text)], max_tokens=18)
        with self.assertRaisesRegex(ValueError, "already a piece"):
            chunk([first], max_tokens=13)

    def test_a_node_that_is_not_from_the_thread_parser_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "SlackThreadParser"):
            chunk([Document(text="ana: a\n" * 20)], max_tokens=10)

    def test_a_ceiling_below_the_metadata_lines_says_so(self):
        with self.assertRaisesRegex(ValueError, "metadata"):
            chunk([thread_node()], max_tokens=5)  # "channel: eng\nparticipants: ana, ben, cai" is 6 words

    def test_pieces_do_not_share_their_link_object(self):
        node = thread_node()
        first, second = chunk([node], max_tokens=16)
        self.assertIsNot(first.relationships[NodeRelationship.SOURCE], second.relationships[NodeRelationship.SOURCE])
        self.assertIsNot(first.relationships[NodeRelationship.SOURCE], node.relationships[NodeRelationship.SOURCE])

    def test_the_tokenizer_survives_pickling_for_parallel_workers(self):
        chunker = pickle.loads(pickle.dumps(SlackMessageChunker(tokenizer=words, max_tokens=16)))
        self.assertEqual(len(chunker.get_nodes_from_documents([thread_node()])), 2)

    def test_every_module_the_message_rules_import_is_in_the_fingerprint(self):
        imported = set(re.findall(r"from pipeline\.slack\.(\w+) import", (ROOT / "pipeline/slack/messages.py").read_text()))
        self.assertLessEqual({f"{module}.py" for module in imported}, set(chunker_module.RULE_FILES))

    def test_library_settings_that_would_change_our_nodes_are_refused(self):
        for setting in ({"include_metadata": True}, {"include_prev_next_rel": True}, {"id_func": lambda i, d: "x"}):
            with self.assertRaises(ValueError):
                SlackMessageChunker(**setting)

    def test_the_ceiling_and_the_rules_are_in_the_cache_key(self):
        nodes = [thread_node()]
        default = get_transformation_hash(nodes, SlackMessageChunker())
        self.assertNotEqual(default, get_transformation_hash(nodes, SlackMessageChunker(max_tokens=512)))
        self.assertNotEqual(default, get_transformation_hash(nodes, SlackMessageChunker(rules_fingerprint="other")))
        self.assertEqual(SlackMessageChunker().max_tokens, 2048)
        self.assertEqual(SlackMessageChunker.class_name(), "SlackMessageChunker")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(chunker_module).failed, 0)


class RealThreads(unittest.TestCase):
    """LlamaIndex's default tokenizer (tiktoken cl100k_base), default ceiling 2,048."""

    def test_novacare_passes_through_unchanged(self):
        [novacare] = [node for node in fixture_nodes(TRUTH_FIXTURES) if node.ref_doc_id == NOVACARE_ID]
        self.assertIs(SlackMessageChunker().get_nodes_from_documents([novacare])[0], novacare)

    def test_the_smallest_real_over_budget_thread_splits_into_two_halves(self):
        [node] = fixture_nodes(FIXTURES)
        pieces = SlackMessageChunker().get_nodes_from_documents([node])
        self.assertEqual([(piece.metadata["first_turn"], piece.metadata["last_turn"]) for piece in pieces],
                         [(0, 19), (20, 39)])
        self.assertEqual([piece.id_ for piece in pieces],
                         ["5f15aa7b-9a60-5b26-8ca2-59132a770bbc", "1764c000-f815-53a0-93c2-7444720cebb6"])
        self.assertTrue(pieces[1].text.startswith("Anna (oncall): eng-runtime (Sam), infra-sre (Maria)"))

    def test_it_runs_after_the_thread_parser_inside_the_ingestion_pipeline(self):
        pipeline = IngestionPipeline(transformations=[SlackThreadParser(), SlackMessageChunker()])
        pieces = pipeline.run(documents=list(thread_documents(FIXTURES)))
        self.assertEqual(len(pieces), 2)
        self.assertEqual({piece.ref_doc_id for piece in pieces}, {OVER_BUDGET_ID})


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_only_the_threads_over_2048_tokens_split(self):
        totals, ids, tokens = Counter(), set(), get_tokenizer()
        parser, chunker = SlackThreadParser(), SlackMessageChunker()
        smallest, largest = None, 0
        for document in thread_documents(CLEAN):
            for node in parser.get_nodes_from_documents([document]):
                pieces = chunker.get_nodes_from_documents([node])
                totals["nodes_in"] += 1
                totals["pieces_out"] += len(pieces)
                totals[f"threads_in_{len(pieces)}"] += 1
                ids.update(piece.id_ for piece in pieces)
                if len(pieces) > 1:
                    sizes = [len(tokens(piece.get_content(MetadataMode.EMBED))) for piece in pieces]
                    smallest, largest = min(smallest or sizes[0], *sizes), max(largest, *sizes)
        self.assertEqual(totals, {"nodes_in": 285_597, "pieces_out": 286_298, "threads_in_1": 284_900,
                                  "threads_in_2": 693, "threads_in_3": 4})
        self.assertEqual(len(ids), 286_298)
        self.assertLessEqual(largest, 2_048)
        self.assertEqual(smallest, 666)  # counted on the embedded text, metadata lines included


if __name__ == "__main__":
    unittest.main()

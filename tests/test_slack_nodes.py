"""SLACK-9: SlackThreadParser, a LlamaIndex NodeParser: one clean-thread Document -> one TextNode.

Run: uv run python -m unittest discover tests
"""
import doctest
import hashlib
import sys
import unittest
from collections import Counter
from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import Document, MetadataMode, NodeRelationship

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import nodes as nodes_module  # noqa: E402
from pipeline.slack.nodes import SlackThreadParser  # noqa: E402

CLEAN = ROOT / "data/slack/clean"
FIXTURES = ROOT / "tests/fixtures/slack_truth"
NOVACARE = "dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-novacare-vra-check.txt"
PIN_THREAD = "dsid_47db1d5b12a44a9885495cde5305c45d__1725550001-pin-extension-sow-thread.txt"
PIN_TEXT = ("product\n\nsam (pm): Heads-up: team asked for a narrower deprecation policy.\n\n"
            "opsbot: ticket created #MC-402 for pin-extension-template.\n")


def thread_document(file_name: str, text: str) -> Document:
    return Document(id_=file_name.split("__")[0].removeprefix("dsid_"), text=text, metadata={"file_name": file_name})


def parse_one(file_name: str, text: str):
    [node] = SlackThreadParser().get_nodes_from_documents([thread_document(file_name, text)])
    return node


class OneThreadOneNode(unittest.TestCase):
    def test_the_embedded_text_is_channel_participants_then_the_messages(self):
        node = parse_one(PIN_THREAD, PIN_TEXT)
        self.assertEqual(node.get_content(MetadataMode.EMBED),
                         "channel: product\nparticipants: sam, opsbot\n\n" + PIN_TEXT.removeprefix("product\n\n").rstrip("\n"))

    def test_bookkeeping_is_on_the_node_but_not_in_the_embedded_text(self):
        node = parse_one(PIN_THREAD, PIN_TEXT)
        self.assertEqual(node.metadata, {
            "channel": "product", "participants": "sam, opsbot", "doc_id": "47db1d5b12a44a9885495cde5305c45d",
            "channel_route": "line1", "first_turn": 0, "last_turn": 1,
            "file_name": PIN_THREAD,
        })
        embedded = node.get_content(MetadataMode.EMBED)
        for hidden in ("47db1d5b", "line1", "first_turn", "last_turn", "file_name", "1725550001"):
            self.assertNotIn(hidden, embedded)

    def test_the_node_links_to_its_document(self):
        node = parse_one(PIN_THREAD, PIN_TEXT)
        self.assertEqual(node.relationships[NodeRelationship.SOURCE].node_id, "47db1d5b12a44a9885495cde5305c45d")
        self.assertEqual(node.ref_doc_id, "47db1d5b12a44a9885495cde5305c45d")

    def test_the_node_id_is_stable(self):
        expected = hashlib.sha256(b"47db1d5b12a44a9885495cde5305c45d:0:1").hexdigest()
        self.assertEqual(parse_one(PIN_THREAD, PIN_TEXT).id_, expected)
        self.assertEqual(parse_one(PIN_THREAD, PIN_TEXT).id_, expected)

    def test_an_unknown_channel_contributes_nothing_to_the_text(self):
        node = parse_one(PIN_THREAD, "1719998880\n\nkai: paging\n")
        self.assertNotIn("channel", node.metadata)
        self.assertEqual(node.get_content(MetadataMode.EMBED), "participants: kai\n\n1719998880\n\nkai: paging")

    def test_a_first_line_that_is_the_threads_own_id_is_dropped(self):
        node = parse_one(PIN_THREAD, "dsid_47db1d5b12a44a9885495cde5305c45d\n\nkai: paging\n")
        self.assertEqual(node.text, "kai: paging\n")

    def test_the_own_id_line_is_dropped_anywhere_in_the_header(self):
        node = parse_one(PIN_THREAD, "product\n\ndsid_47db1d5b12a44a9885495cde5305c45d\n\nkai: paging\n")
        self.assertEqual(node.text, "kai: paging\n")

    def test_the_llm_sees_the_doc_id_to_cite_but_not_the_bookkeeping(self):
        text = parse_one(PIN_THREAD, PIN_TEXT).get_content(MetadataMode.LLM)
        self.assertIn("doc_id: 47db1d5b12a44a9885495cde5305c45d", text)
        self.assertNotIn("channel_route", text)

    def test_text_before_the_first_message_is_kept(self):
        text = "support\n\nCustomer escalated: tool routing broken.\n\nSDK: go-sdk v0.9.8\n"
        node = parse_one(PIN_THREAD, text)
        self.assertEqual(node.text, text.removeprefix("support\n\n"))
        self.assertEqual(node.metadata["participants"], "")
        self.assertNotIn("first_turn", node.metadata)

    def test_every_metadata_value_is_flat(self):
        for text in (PIN_TEXT, "support\n\nno speaker here\n", "1719998880\n\nkai: paging\n"):
            for value in parse_one(PIN_THREAD, text).metadata.values():
                self.assertIsInstance(value, (str, int, float), text)

    def test_asking_for_a_progress_bar_changes_nothing_else(self):
        document = thread_document(PIN_THREAD, PIN_TEXT)
        quiet = SlackThreadParser().get_nodes_from_documents([document])
        with_bar = SlackThreadParser().get_nodes_from_documents([document], show_progress=True)
        self.assertEqual([node.to_dict() for node in with_bar], [node.to_dict() for node in quiet])

    def test_a_document_whose_id_is_not_the_thread_id_is_an_error(self):
        for wrong_id in ("9f6c813e-d05f-4c1e-9a36-5e2b8f0c1d7a", "/Users/deepak/data/slack/clean/" + PIN_THREAD):
            document = Document(id_=wrong_id, text=PIN_TEXT, metadata={"file_name": PIN_THREAD})
            with self.assertRaises(ValueError, msg=wrong_id):
                SlackThreadParser().get_nodes_from_documents([document])

    def test_a_document_field_named_like_ours_does_not_hide_ours(self):
        document = thread_document(PIN_THREAD, PIN_TEXT)
        document.metadata["channel"] = "not-this-one"
        [node] = SlackThreadParser().get_nodes_from_documents([document])
        self.assertTrue(node.get_content(MetadataMode.EMBED).startswith("channel: product\n"))

    def test_a_document_without_a_file_name_is_an_error(self):
        with self.assertRaises(KeyError):
            SlackThreadParser().get_nodes_from_documents([Document(id_="x", text="eng\n\nkai: hi\n")])

    def test_doctests(self):
        self.assertEqual(doctest.testmod(nodes_module).failed, 0)


class InsideTheLibrary(unittest.TestCase):
    def test_it_runs_as_a_transformation_on_documents_from_simple_directory_reader(self):
        documents = SimpleDirectoryReader(input_files=[FIXTURES / NOVACARE]).load_data()  # default metadata
        for document in documents:
            document.id_ = "a4e702bd03254699b0e7bed0000972ab"
        [node] = IngestionPipeline(transformations=[SlackThreadParser()]).run(documents=documents)
        self.assertTrue(node.get_content(MetadataMode.EMBED).startswith(
            "channel: customer-success\nparticipants: Aisha, Priya, Ben, Tom, questionnaire-bot\n\nAisha (CS): Hey team"))
        self.assertEqual(node.ref_doc_id, "a4e702bd03254699b0e7bed0000972ab")
        self.assertEqual(sorted(node.metadata), ["channel", "channel_route", "doc_id", "file_name", "first_turn",
                                                 "last_turn", "participants"])  # none of the reader's other fields
        for leaked in ("file_path", "file_size", "creation_date", "last_modified_date", "dsid_"):
            self.assertNotIn(leaked, node.get_content(MetadataMode.EMBED))
            self.assertNotIn(leaked, node.get_content(MetadataMode.LLM))


@unittest.skipUnless(CLEAN.is_dir(), "clean Slack corpus not present (run python -m pipeline.slack.corpus)")
class RealCorpus(unittest.TestCase):
    def test_every_thread_becomes_one_node(self):
        totals, node_ids, parser = Counter(), set(), SlackThreadParser()
        for path in CLEAN.glob("*.txt"):
            [node] = parser.get_nodes_from_documents([thread_document(path.name, path.read_text(encoding="utf-8"))])
            embedded = node.get_content(MetadataMode.EMBED)
            node_ids.add(node.id_)
            totals["nodes"] += 1
            totals["without_channel"] += "channel" not in node.metadata
            totals["without_participants"] += not node.metadata["participants"]
            totals["doc_id_in_embedded_text"] += node.metadata["doc_id"] in embedded
        self.assertEqual(totals, {"nodes": 285_605, "without_channel": 9_053, "without_participants": 64,
                                  "doc_id_in_embedded_text": 0})
        self.assertEqual(len(node_ids), 285_605)


if __name__ == "__main__":
    unittest.main()

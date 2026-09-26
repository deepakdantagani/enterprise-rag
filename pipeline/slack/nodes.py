r"""SLACK-9: SlackThreadParser, a LlamaIndex NodeParser: one clean-thread Document -> one TextNode.

It runs as a step inside LlamaIndex's IngestionPipeline, like SentenceSplitter does. LlamaIndex
calls `get_nodes_from_documents`, which calls our `_parse_nodes` and then tidies up. We only
turn a Document into a TextNode, with SLACK-8's `parse_thread`; no new rules here.

No LlamaIndex parser splits chat by speaker (SentenceSplitter, TokenTextSplitter and the
semantic splitters cut by size or meaning; Markdown/JSON/HTML parsers by markup), so this
wrapper is ours. The rendering is the library's: a TextNode already writes
`{metadata_str}\n\n{content}` with one `key: value` line per metadata field, and leaves
out `excluded_embed_metadata_keys`. So we set fields; we build no header string.

What the embedder sees:

    channel: customer-success
    participants: Aisha, Priya, Ben, Tom, questionnaire-bot

    Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment...

Only `channel` and `participants` are embedded: an identical prefix on every node pulls the
285,605 vectors together, so the prefix carries only what has meaning. `channel` is left out
when it is unknown (9,053 threads). Roles need no field; they are in the speaker lines.

A complete node, for reference: the real NovaCare thread, read with SimpleDirectoryReader's
defaults (tests/fixtures/slack_truth/, dsid_a4e702bd...__1793045678-novacare-vra-check.txt).

1. What each reader of the node sees (LlamaIndex renders these from the fields below)

    embedding model, get_content(MetadataMode.EMBED):
        channel: customer-success
        participants: Aisha, Priya, Ben, Tom, questionnaire-bot

        Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment...

    answering LLM, get_content(MetadataMode.LLM): the same, plus one line to cite from:
        doc_id: a4e702bd03254699b0e7bed0000972ab

2. Identity and text

    id_             bb4f104c-ce43...      ours: uuid5 of "a4e702bd...:0:15", same every run
    text            "Aisha (CS): Hey team..."  ours: the clean file minus "customer-success\n\n"
    start_char_idx  18                         library: where the text starts in the Document
    end_char_idx    2192                       library: where it ends
    embedding       None                       library: filled by the embed model (SLACK-11)

3. metadata: 7 keys, all set by us, and who sees each (no timestamp; no empty values)

    key            value                                      from                   seen by
    channel        customer-success                           channel_of (SLACK-5)   embed + LLM
    participants   Aisha, Priya, Ben, Tom, questionnaire-bot  speakers (SLACK-7/8)   embed + LLM
    doc_id         a4e702bd03254699b0e7bed0000972ab           file name (SLACK-8)    LLM only
    channel_route  line1                                      channel_of (SLACK-5)   hidden
    first_turn     0                                          turn_range             hidden
    last_turn      15                                         turn_range             hidden
    slug           novacare-vra-check                         file name (SLACK-8)    hidden

    "hidden" is set by two lists on the node:
    excluded_embed_metadata_keys  every key except channel and participants
    excluded_llm_metadata_keys    the same, minus doc_id
    The reader's other fields (file_path, file_size, creation_date, ...) are not copied onto
    the node (include_metadata=False): a laptop path and a file-copy date mean nothing here.
    A key with no value is left out: no first_turn/last_turn/participants when nobody speaks
    (56 threads), no channel when unknown;
    a file name without a slug (6,199), no slug. file_name is not kept: it carries the fake
    timestamp (1793045678), and doc_id + slug already lead back to the file.

4. Link to the Document, and library defaults

    relationships[SOURCE]  node_id  a4e702bd0325...   the Document's id; must be the dsid
                           type     DOCUMENT
                           hash     5dcf1544...       library: sha256(text + metadata) of the
                                                      Document; tells the docstore if it changed
                           metadata {file_name}: all thread_documents keeps
    metadata_template   "{key}: {value}"               library defaults, not set by us
    metadata_separator  "\n"
    text_template       "{metadata_str}\n\n{content}"
    mimetype            text/plain

The node text is the thread minus its channel line; on an unknown-channel thread, minus a
line 1 that is the export's file name (it starts with the file name's fake timestamp:
`1719998880`, `3476543210-launch-wedge-preflight.json`; 6,577 threads); and minus any line that
is only the thread's own id (`dsid_02f44014...`: 151 threads, on line 1 in 148 and on line 3 in
7, 4 of them both). The rest of the header stays: 157 threads carry real text there (a summary,
an odd speaker line). 8 threads have no text left at all (only a channel line or their own id)
and make no node; 56 more have text but no message.

    >>> node_id("47db1d5b12a44a9885495cde5305c45d", 0, 5)
    'ae24d386-a511-535f-869a-023fc0e21d78'
"""
import hashlib
import uuid
from pathlib import Path
from typing import Any, List, Optional, Sequence

from llama_index.core.node_parser import NodeParser
from llama_index.core.node_parser.node_utils import default_id_func
from llama_index.core.schema import BaseNode, MetadataMode, NodeRelationship, TextNode
from llama_index.core.utils import get_tqdm_iterable
from pydantic import Field, model_validator

from pipeline.slack.channel import UNKNOWN
from pipeline.slack.thread import THREAD_FILE_NAME, Thread, parse_thread

HIDDEN_FROM_EMBEDDING = ["doc_id", "channel_route", "first_turn", "last_turn", "slug"]
HIDDEN_FROM_LLM = ["channel_route", "first_turn", "last_turn", "slug"]  # doc_id stays, to cite
NODE_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "enterprise-rag/slack/nodes")
RULE_FILES = ("channel.py", "messages.py", "speaker.py", "thread.py", "nodes.py")  # what a node depends on


def rules_fingerprint() -> str:
    """sha256 of the rule files: part of the parser's settings, so of IngestionPipeline's cache
    key. A cache kept across runs then misses after any rule change instead of replaying old nodes."""
    here = Path(__file__).parent
    return hashlib.sha256(b"".join((here / name).read_bytes() for name in RULE_FILES)).hexdigest()


class SlackThreadParser(NodeParser):
    """One TextNode per clean Slack thread Document (from `thread_documents`).

    Each Document must be a root Document with `file_name` in its metadata and the thread's
    dsid as its id: the docstore recognises a thread on a re-run by that id.
    """

    include_metadata: bool = Field(default=False, description="Our node sets its own metadata.")
    include_prev_next_rel: bool = Field(default=False, description="One node per thread: nothing to link.")
    rules_fingerprint: str = Field(default_factory=rules_fingerprint, description="Changes the cache key.")

    @classmethod
    def class_name(cls) -> str:
        return "SlackThreadParser"

    @model_validator(mode="after")
    def refuse_settings_that_would_change_our_nodes(self) -> "SlackThreadParser":
        if self.include_metadata or self.id_func is not default_id_func:
            raise ValueError("SlackThreadParser sets its own metadata and ids; "
                             "include_metadata and id_func cannot be changed")
        return self

    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        documents = get_tqdm_iterable(nodes, show_progress, "Parsing Slack threads")  # the library's bar
        return [node for document in documents for node in thread_nodes(document)]


def thread_nodes(document: BaseNode) -> List[TextNode]:
    """The node for one thread Document, or none when no text is left (8 threads hold only a
    channel line or their own id: a node would embed nothing but metadata)."""
    if document.source_node is not None:
        raise ValueError(f"{document.id_!r} is not a root thread Document: it already has a source "
                         f"({document.source_node.node_id!r}); SlackThreadParser takes Documents from "
                         "thread_documents, before any splitter")
    file_name = document.metadata["file_name"]
    text = document.get_content(MetadataMode.NONE)
    thread = parse_thread(file_name, text)
    if document.id_ != thread.doc_id:
        raise ValueError(f"Document id must be the thread's dsid {thread.doc_id!r}, got {document.id_!r}")
    kept = node_text(text, thread, THREAD_FILE_NAME.fullmatch(file_name)["timestamp"])
    if not kept.strip():
        return []
    first_turn, last_turn = turn_range(thread)
    return [TextNode(
        id_=node_id(thread.doc_id, first_turn, last_turn),
        text=kept,
        metadata=node_metadata(thread, first_turn, last_turn),
        excluded_embed_metadata_keys=list(HIDDEN_FROM_EMBEDDING),
        excluded_llm_metadata_keys=list(HIDDEN_FROM_LLM),
        relationships={NodeRelationship.SOURCE: document.as_related_node_info()},
    )]


def turn_range(thread: Thread) -> tuple[Optional[int], Optional[int]]:
    """First and last message turn in the node, as parse_thread numbered them; (None, None) for
    a thread with no message."""
    return (thread.messages[0].turn, thread.messages[-1].turn) if thread.messages else (None, None)


def node_id(doc_id: str, first_turn: Optional[int], last_turn: Optional[int]) -> str:
    """A UUID from doc_id:first_turn:last_turn, the same on every run (UUID-shaped because Qdrant
    and Weaviate accept nothing else). SLACK-10 reuses it per piece."""
    return str(uuid.uuid5(NODE_ID_NAMESPACE, f"{doc_id}:{first_turn}:{last_turn}"))


def node_text(text: str, thread: Thread, timestamp: str) -> str:
    """The thread without its channel line, without a line 1 that is the export's file name
    (it starts with the file name's fake timestamp: `3476543210-launch-wedge-preflight.json`),
    and without any line that is only its own id."""
    first_line, _, rest = text.partition("\n")
    if thread.channel.route != UNKNOWN or is_export_file_name(first_line, timestamp):
        text = rest
    own_id = f"dsid_{thread.doc_id}"
    if own_id not in text:
        return text.lstrip("\n")
    return "".join(line for line in text.splitlines(keepends=True) if line.strip() != own_id).lstrip("\n")


def is_export_file_name(line: str, timestamp: str) -> bool:
    """True for `1719998880` or `1719998880-some-slug.json` when 1719998880 is this file's own
    timestamp: an export artefact, not something anyone said.

    >>> is_export_file_name("3476543210-launch-wedge-preflight.json", "3476543210")
    True
    >>> is_export_file_name("3476543210 is the ticket number", "3476543210")
    False
    """
    line = line.strip()
    return line.startswith(timestamp) and not any(character.isspace() for character in line)


def node_metadata(thread: Thread, first_turn: Optional[int], last_turn: Optional[int]) -> dict:
    """Flat values only (str, int), as LlamaIndex's docs ask for vector stores; a field with no
    value is left out, never empty or None: channel when unknown, participants and turns when
    nobody speaks, slug when the file name has none."""
    fields = {"channel": thread.channel.name if thread.channel.route != UNKNOWN else None,
              "participants": ", ".join(thread.participants) or None,
              "doc_id": thread.doc_id, "channel_route": thread.channel.route,
              "first_turn": first_turn, "last_turn": last_turn, "slug": thread.slug}
    return {key: value for key, value in fields.items() if value is not None}

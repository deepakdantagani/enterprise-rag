"""SLACK-9: SlackThreadParser, a LlamaIndex NodeParser: one clean-thread Document -> one TextNode.

It runs as a step inside LlamaIndex's IngestionPipeline, like SentenceSplitter does. LlamaIndex
calls `get_nodes_from_documents`, which calls our `_parse_nodes` and then tidies up. We only
turn a Document into a TextNode, with SLACK-8's `parse_thread`; no new rules here.

No LlamaIndex parser splits chat by speaker (SentenceSplitter, TokenTextSplitter and the
semantic splitters cut by size or meaning; Markdown/JSON/HTML parsers by markup), so this
wrapper is ours. The rendering is the library's: a TextNode already writes
`{metadata_str}\\n\\n{content}` with one `key: value` line per metadata field, and leaves
out `excluded_embed_metadata_keys`. So we set fields; we build no header string.

What the embedder sees:

    channel: customer-success
    participants: Aisha, Priya, Ben, Tom, questionnaire-bot

    Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment...

Only `channel` and `participants` are embedded: an identical prefix on every node pulls the
285,605 vectors together, so the prefix carries only what has meaning. `channel` is left out
when it is unknown (9,053 threads). Roles need no field; they are in the speaker lines.

The node text is the thread minus its channel line, and minus any line that is only the
thread's own id (`dsid_02f44014...`: line 1 in 151 threads, line 3 in 7 more). The rest of the header stays: 157 threads carry real text
there (a summary, an odd speaker line) and 64 have no message at all.

    >>> node_id("47db1d5b12a44a9885495cde5305c45d", 0, 5)[:12]
    '18577a92a262'
"""
import hashlib
from typing import Any, List, Optional, Sequence

from llama_index.core.node_parser import NodeParser
from llama_index.core.schema import BaseNode, NodeRelationship, TextNode

from pipeline.slack.thread import Thread, parse_thread

HIDDEN_FROM_EMBEDDING = ["doc_id", "channel_route", "first_turn", "last_turn"]
HIDDEN_FROM_LLM = ["channel_route", "first_turn", "last_turn"]  # doc_id stays, to cite
# Every key of the Document is hidden too: LlamaIndex copies the Document's metadata onto the
# node, and SimpleDirectoryReader's defaults (file_path, file_size, creation_date, ...) would
# otherwise put the file name, a fake timestamp and file-system dates into every vector.
CHANNEL_ON_LINE_1 = frozenset({"line1", "export_path"})  # SLACK-5 routes where line 1 is not content


class SlackThreadParser(NodeParser):
    """One TextNode per clean Slack thread. Needs `file_name` in each Document's metadata."""

    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        return [thread_node(document) for document in nodes]


def thread_node(document: BaseNode) -> TextNode:
    """The node for one thread Document: its text, its metadata, a stable id, a link back."""
    thread = parse_thread(document.metadata["file_name"], document.text)
    first_turn, last_turn = turn_range(thread)
    return TextNode(
        id_=node_id(thread.doc_id, first_turn, last_turn),
        text=node_text(document.text, thread),
        metadata=node_metadata(thread, first_turn, last_turn),
        excluded_embed_metadata_keys=[*HIDDEN_FROM_EMBEDDING, *document.metadata],
        excluded_llm_metadata_keys=[*HIDDEN_FROM_LLM, *document.metadata],
        relationships={NodeRelationship.SOURCE: document.as_related_node_info()},
    )


def turn_range(thread: Thread) -> tuple[Optional[int], Optional[int]]:
    """First and last message turn in the node; (None, None) for a thread with no message."""
    return (0, len(thread.messages) - 1) if thread.messages else (None, None)


def node_id(doc_id: str, first_turn: Optional[int], last_turn: Optional[int]) -> str:
    """sha256 of doc_id:first_turn:last_turn: the same on every run. SLACK-10 reuses it per piece."""
    return hashlib.sha256(f"{doc_id}:{first_turn}:{last_turn}".encode()).hexdigest()


def node_text(text: str, thread: Thread) -> str:
    """The thread without its channel line and without any line that is only its own id."""
    if thread.channel.route in CHANNEL_ON_LINE_1:
        text = text.partition("\n")[2]
    own_id = f"dsid_{thread.doc_id}"
    return "".join(line for line in text.splitlines(keepends=True) if line.strip() != own_id).lstrip("\n")


def node_metadata(thread: Thread, first_turn: Optional[int], last_turn: Optional[int]) -> dict:
    """Flat fields only (str, int, None): vector stores reject lists, so participants is joined."""
    channel = {"channel": thread.channel.name} if thread.channel.route in CHANNEL_ON_LINE_1 else {}
    return {**channel, "participants": ", ".join(thread.participants), "doc_id": thread.doc_id,
            "channel_route": thread.channel.route, "first_turn": first_turn, "last_turn": last_turn}

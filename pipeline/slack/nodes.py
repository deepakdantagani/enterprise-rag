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

A complete node, for reference: the real NovaCare thread, read with SimpleDirectoryReader's
defaults (text shortened; the rest printed as the code builds it). Where each key comes from:
[ours] this module, [reader] SimpleDirectoryReader, copied onto the node by LlamaIndex,
[lib] LlamaIndex itself.

    TextNode(
      id_='baf7ae0d43d3e0f6...',            [ours] sha256("a4e702bd...:0:15"), same every run
      embedding=None,                       [lib] filled by the embed model (SLACK-11)
      metadata={
        'file_path': '.../dsid_a4e702bd...novacare-vra-check.txt',   [reader] hidden
        'file_name': 'dsid_a4e702bd...__1793045678-novacare-vra-check.txt',  [reader] hidden
        'file_type': 'text/plain', 'file_size': 2202,                [reader] hidden (bytes)
        'creation_date': '2026-09-25', 'last_modified_date': '2026-09-25',
                                            [reader] hidden: the file's copy date, not the chat's
        'channel': 'customer-success',      [ours] channel_of, SLACK-5; embedded
        'participants': 'Aisha, Priya, Ben, Tom, questionnaire-bot',
                                            [ours] speakers, SLACK-7/8, joined; embedded
        'doc_id': 'a4e702bd03254699b0e7bed0000972ab',   [ours] file name, SLACK-8; LLM only
        'channel_route': 'line1',           [ours] SLACK-5; hidden (SLACK-12 splits on it)
        'first_turn': 0, 'last_turn': 15},  [ours] turn_range; hidden
      excluded_embed_metadata_keys=['doc_id', 'channel_route', 'first_turn', 'last_turn',
        'file_path', 'file_name', 'file_type', 'file_size', 'creation_date', 'last_modified_date'],
      excluded_llm_metadata_keys=[the same, minus 'doc_id'],
      relationships={SOURCE: RelatedNodeInfo(node_id='a4e702bd...', node_type=DOCUMENT,
                                             metadata={the 6 file fields}, hash='5dcf1544...')},
                                            [ours] the link; [lib] its type, copy and hash
      text="Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment...
            ...questionnaire-bot: Thread closed by inactivity after 48h (reminder set for 2026-03-30).\n",
                                            [ours] node_text: the clean file minus 'customer-success\n\n'
      start_char_idx=18, end_char_idx=2192, [lib] where the text sits in the Document
      metadata_template='{key}: {value}', metadata_separator='\n',
      text_template='{metadata_str}\n\n{content}', mimetype='text/plain')   [lib] defaults

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
from llama_index.core.utils import get_tqdm_iterable

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
        documents = get_tqdm_iterable(nodes, show_progress, "Parsing Slack threads")  # the library's bar
        return [thread_node(document) for document in documents]


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
    """Flat values only (str, int), as LlamaIndex's docs ask for vector stores: participants is
    joined into one string, and a field with no value is left out rather than set to None
    (channel when unknown, the turns when the thread has no message)."""
    channel = {"channel": thread.channel.name} if thread.channel.route in CHANNEL_ON_LINE_1 else {}
    turns = {"first_turn": first_turn, "last_turn": last_turn} if thread.messages else {}
    return {**channel, "participants": ", ".join(thread.participants), "doc_id": thread.doc_id,
            "channel_route": thread.channel.route, **turns}

"""SLACK-10: SlackMessageChunker, a LlamaIndex NodeParser: a node over the token ceiling -> nodes cut
between messages, never inside one.

It runs after SlackThreadParser in the IngestionPipeline:
`transformations=[SlackThreadParser(), SlackMessageChunker(), embed_model]`. A node at or under the
ceiling comes back as the same object; 284,900 of the 285,597 nodes do at the default 2,048.

Tokens are counted on what the embedder sees (`get_content(MetadataMode.EMBED)`: the channel and
participants lines plus the text), with LlamaIndex's default tokenizer (tiktoken cl100k_base)
unless SLACK-11 passes the embedding model's own. Measured over all nodes: p50 831, p90 1,254,
p99 1,714, max 4,143 tokens; no single message is over 2,048 (the longest is 1,752), so
SentenceSplitter is never needed and a message longer than the ceiling is an error.

The real example: dsid_19189bd1...-stream-protocol-paging-rca-coord, the smallest thread over the
ceiling (2,049 tokens, 40 messages). Cutting as late as possible, as SentenceSplitter packs, gives
2,008 + 15 tokens: a lone "noted, will ping" piece (279 pieces under 200 tokens across the corpus).
Cutting where the pieces come out most equal gives turns 0-19 and 20-39, about 1,025 and 1,050.

Each piece keeps the thread's fields (channel, participants: the whole thread's, doc_id, ...),
gets its own first_turn/last_turn and the id `node_id(doc_id, first_turn, last_turn)`, and links
to the thread Document, so the docstore still replaces every piece of a thread on a re-run.

Give it whole-thread nodes, once. A piece may not re-split into its turns: `maria gonzalez:`
counts as a speaker only when the name opens 2 lines, and inside one piece it may open 1
(32 of 6,770 real pieces at a 512 ceiling). Chunking a piece again to a lower ceiling is an error;
at the same ceiling every piece already fits and passes through.

The tokenizer is not part of the cache key (as in SentenceSplitter): a cache kept across runs
must be cleared when the tokenizer changes.
"""
from functools import cache
from itertools import accumulate
from typing import Any, Callable, List, Sequence

from llama_index.core.schema import BaseNode, MetadataMode, NodeRelationship, TextNode
from llama_index.core.utils import get_tokenizer, get_tqdm_iterable
from pydantic import Field

from pipeline.slack.messages import split_messages
from pipeline.slack.nodes import SlackNodeParser, node_id, rules_fingerprint

DEFAULT_MAX_TOKENS = 2048
RULE_FILES = ("whitespace.py", "messages.py", "nodes.py", "chunker.py")  # where cuts, ids and fields come from


class SlackMessageChunker(SlackNodeParser):
    """Cuts every SlackThreadParser node over `max_tokens` between messages into the fewest,
    most equal pieces that each fit; passes every other node through untouched."""

    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0, description="The ceiling, in embedded tokens.")
    rules_fingerprint: str = Field(default_factory=lambda: rules_fingerprint(RULE_FILES),
                                   description="Changes the cache key.")
    tokenizer: Callable[[str], Sequence] = Field(
        default_factory=get_tokenizer, exclude=True,  # a field, so it survives pickling for num_workers
        description="Text -> tokens; LlamaIndex's default (tiktoken cl100k_base) unless the embed model's is given.")

    @classmethod
    def class_name(cls) -> str:
        return "SlackMessageChunker"

    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        nodes = get_tqdm_iterable(nodes, show_progress, "Chunking Slack threads")
        return [piece for node in nodes for piece in self.pieces(node)]

    def pieces(self, node: BaseNode) -> List[BaseNode]:
        """[node] when it fits; otherwise the fewest balanced pieces that all fit."""
        if self.fits(node):
            return [node]
        units = message_units(node)
        one_per_message = pieces_at(node, units, list(range(1, len(units))))
        if not all(self.fits(piece) for piece in one_per_message):
            if not self.fits(piece_node(node, [""], 0, 1)):
                raise ValueError(f"the metadata lines alone are over the ceiling of {self.max_tokens} tokens")
            raise ValueError(f"thread {node.metadata['doc_id']} has a message longer than the ceiling "
                             f"of {self.max_tokens} tokens; cutting inside a message is not built")
        sizes = [len(self.tokenizer(unit)) for unit in units]
        for count in range(2, len(units)):
            pieces = pieces_at(node, units, balanced_cuts(sizes, count))
            if all(self.fits(piece) for piece in pieces):
                return pieces
        return one_per_message

    def fits(self, node: BaseNode) -> bool:
        return len(self.tokenizer(node.get_content(MetadataMode.EMBED))) <= self.max_tokens


def message_units(node: BaseNode) -> List[str]:
    """The node text cut before every message; text before the first message stays with it.
    SLACK-9's own split, redone on the node text: it finds the same messages in all 285,597 nodes,
    and a node where it does not (a piece, or rules changed since the node was made) is an error."""
    if "doc_id" not in node.metadata or node.source_node is None:
        raise ValueError(f"node {node.node_id} is not from SlackThreadParser: SlackMessageChunker comes after it")
    split = split_messages(node.get_content(MetadataMode.NONE))
    if not split.messages:
        raise ValueError(f"node {node.node_id} is over the ceiling and has no message to cut between")
    first_turn, last_turn = node.metadata["first_turn"], node.metadata["last_turn"]
    if len(split.messages) != last_turn - first_turn + 1:
        raise ValueError(f"node {node.node_id} holds {len(split.messages)} messages but its turns are "
                         f"{first_turn}..{last_turn}: it is already a piece (chunk whole threads, once), "
                         "or the message rules changed since it was made")
    return [split.header + split.messages[0], *split.messages[1:]]


def balanced_cuts(sizes: Sequence[int], pieces: int) -> List[int]:
    """Where each piece after the first starts, so that `pieces` runs of `sizes` have the smallest
    largest run (then the most even spread): every item stays whole and in order.

    >>> balanced_cuts([4, 4, 3, 5], 2)
    [2]
    >>> balanced_cuts([10, 1, 1, 1, 1], 2)
    [1]
    >>> balanced_cuts([2, 8, 5, 2, 1, 5, 1], 4)
    [1, 2, 4]
    """
    ends = list(accumulate(sizes, initial=0))

    @cache
    def best(start: int, left: int) -> tuple:
        """(largest run, sum of squared runs, cuts) for sizes[start:] in `left` runs."""
        if left == 1:
            size = ends[-1] - ends[start]
            return size, size * size, ()
        options = []
        for cut in range(start + 1, len(sizes) - left + 2):
            size = ends[cut] - ends[start]
            largest, spread, cuts = best(cut, left - 1)
            options.append((max(size, largest), spread + size * size, (cut, *cuts)))
        return min(options)

    return list(best(0, pieces)[2])


def pieces_at(node: BaseNode, units: List[str], cuts: List[int]) -> List[TextNode]:
    bounds = [0, *cuts, len(units)]
    return [piece_node(node, units, start, end) for start, end in zip(bounds, bounds[1:])]


def piece_node(node: BaseNode, units: List[str], start: int, end: int) -> TextNode:
    """Messages start..end-1 of `node` as a node of their own: the thread's fields, its own turns
    and id, the same link to the thread Document, and where it sits in that Document's text."""
    first_turn = node.metadata["first_turn"] + start
    last_turn = node.metadata["first_turn"] + end - 1
    text = "".join(units[start:end])
    begins = None if node.start_char_idx is None else node.start_char_idx + sum(map(len, units[:start]))
    return TextNode(
        id_=node_id(node.metadata["doc_id"], first_turn, last_turn),
        text=text,
        metadata={**node.metadata, "first_turn": first_turn, "last_turn": last_turn},
        excluded_embed_metadata_keys=list(node.excluded_embed_metadata_keys),
        excluded_llm_metadata_keys=list(node.excluded_llm_metadata_keys),
        relationships={NodeRelationship.SOURCE: node.relationships[NodeRelationship.SOURCE].model_copy()},
        start_char_idx=begins,
        end_char_idx=None if begins is None else begins + len(text),
    )

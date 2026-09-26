"""SLACK-10: EmbeddingWindowGuard, a pass-through LlamaIndex TransformComponent: stop the run when a
node is over the embedding model's window, instead of letting the model cut it short.

One node per thread, never split (decision 0002): every thread fits an 8k window. Measured over
all 285,597 nodes with LlamaIndex's default tokenizer on the embedded text: p50 831, p99 1,714,
max 4,143 tokens (dsid_8801a66c...-cloud-escalation-gcp-network-outage, 86 messages). At a 2,048
window 697 nodes would be over; at 8,192 none.

The risk it guards: an embedding model given more than its window drops the rest without an
error (Ollama at its `num_ctx`, `HuggingFaceEmbedding` at `max_length`), so a thread would lose
its last messages from the vector unnoticed. No LlamaIndex component checks this. It sits just
before the embed model:

    IngestionPipeline(transformations=[SlackThreadParser(), EmbeddingWindowGuard(max_tokens, tokenizer), embed_model])

The size is what the embedder reads, `get_content(MetadataMode.EMBED)`: the metadata lines plus
the text.

    >>> guard = EmbeddingWindowGuard(max_tokens=3, tokenizer=str.split)
    >>> guard.embedded_tokens(TextNode(text="three short words"))
    3
    >>> guard.too_long([TextNode(id_="n1", text="four words are here")])
    [('n1', 4)]
"""
from typing import Any, Callable, List, Sequence, Tuple

from llama_index.core.schema import BaseNode, MetadataMode, TextNode, TransformComponent  # noqa: F401  (TextNode: doctest)
from llama_index.core.utils import get_tokenizer
from pydantic import Field

DEFAULT_WINDOW = 8192  # OpenAI text-embedding-3 is 8,191; bge-m3, nomic, arctic-embed2 8,192; Qwen3-Embedding 32k


class EmbeddingWindowGuard(TransformComponent):
    """Returns the nodes unchanged when each fits `max_tokens`; otherwise raises, naming every
    node that does not. `max_tokens` and `tokenizer` are the embedding model's."""

    max_tokens: int = Field(default=DEFAULT_WINDOW, gt=0, description="The embedding model's window, in its tokens.")
    tokenizer: Callable[[str], Sequence] = Field(
        default_factory=get_tokenizer, exclude=True,  # a field, so it survives pickling for num_workers
        description="Text -> tokens; LlamaIndex's default (tiktoken cl100k_base) unless the model's is given.")

    @classmethod
    def class_name(cls) -> str:
        return "EmbeddingWindowGuard"

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        over = self.too_long(nodes)
        if over:
            named = ", ".join(f"{name} ({tokens} tokens)" for name, tokens in over)
            raise ValueError(f"{len(over)} nodes are over the embedding window of {self.max_tokens} tokens "
                             f"and would be cut short: {named}")
        return nodes

    def too_long(self, nodes: Sequence[BaseNode]) -> List[Tuple[str, int]]:
        """(thread doc_id, or node id when there is none; embedded tokens) for each node over the window."""
        sizes = ((node, self.embedded_tokens(node)) for node in nodes)
        return [(node.metadata.get("doc_id", node.node_id), tokens) for node, tokens in sizes
                if tokens > self.max_tokens]

    def embedded_tokens(self, node: BaseNode) -> int:
        return len(self.tokenizer(node.get_content(MetadataMode.EMBED)))

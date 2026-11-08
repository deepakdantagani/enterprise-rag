"""RET-10a: search_snippets, ranked chunks as one block per document: the text the agent's search tool returns.
RET-10b: read_document, a whole document by id, the text the agent's read tool returns.

The agent loop (RET-10) searches with the same hybrid retriever and reranker as today, but a
model has to read the result and decide what to do next, and the raw result is 50 to 200 chunks
of about 512 tokens each. A long document matches in several places: for qst_0001 ("default
size limits for file uploads … multipart upload support …") the gold pull request holds the
chunks ranked #1, #2 and #8, and 14 chunks cover 10 documents. Shown raw, 10 documents with two
full chunks each are 6.7K tokens per search (median over the 470 questions, p90 9.2K).

So a search returns one block per document, in the order of each document's best chunk, at most
10 documents: the title, source and doc_id, how many chunks matched and how many are shown, then
up to 2 snippets of 400 characters, each from where the chunk matched, not from the top of the
document; `(rank N)` is the chunk's 1-based position in `ranked`, `[N]` the block's. That is 1.6K
tokens per search; the agent reads the whole document with the read tool
(RET-10b) when it picks one. Chunks that start with the document's title (51% of them, EVAL-3i
put titles in the text) lose that line so a snippet starts with content. Documents already read
or already shown in an earlier search of the same question are marked, PipesHub's "you have N of
M blocks" and "shown passages give way to new ones" in our words.

    >>> from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode
    >>> def chunk(doc_id, text):
    ...     node = TextNode(text=text, relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)})
    ...     return NodeWithScore(node=node, score=1.0)
    >>> titles = {"dsid_a": ("github", "Multipart PR"), "dsid_b": ("slack", "docs")}
    >>> print(search_snippets([chunk("dsid_a", "Multipart PR\\n\\n10MiB per file"), chunk("dsid_b", "sam: 415s"),
    ...                        chunk("dsid_a", "review: 25MB?")], titles, read={"dsid_b"}))
    [1] Multipart PR | github | dsid_a | 2 chunks matched, 2 shown
      (rank 1) 10MiB per file
      (rank 3) review: 25MB?
    [2] docs | slack | dsid_b | 1 chunk matched, 1 shown (read)
      (rank 2) sam: 415s

RET-10b: once the agent picks a document it reads the whole text, because today's misses sit in
the same document outside the matched chunk (part of a list, a step without its condition).
Documents are small: p50 4,276 characters, p99 11,846; only 22 of 511,962 exceed 30,000, all
Fireflies transcripts (the longest 41,317, "Incident taxonomy working session (v1)"). Those come
back as windows of 30,000 characters that end at a line break, so a "[25:22] Allison Grant: …"
line is never split, with a note saying how much follows and the next `start`. The corpus is one
1.4 GB parquet row group, so a read from disk scans it all (2.1 s): reads go through a dict the
runner (RET-10d) prefetches with each question's candidates, and a miss scans once and is kept.
An unknown id gets a sentence, not an exception: the agent may mistype an id, and the loop must
go on. An id that names two documents (4 do) returns both, as documents_by_id joins them (GEN-2b).

    >>> docs = {"dsid_s": ("Rollback runbook", "Step 1: stop traffic.\\nStep 2: roll back.")}
    >>> print(read_document("dsid_s", docs))
    # Rollback runbook
    <BLANKLINE>
    Step 1: stop traffic.
    Step 2: roll back.
    >>> print(read_document("dsid_s", docs, chars=25))
    # Rollback runbook
    <BLANKLINE>
    Step 1: stop traffic.
    <BLANKLINE>
    … 18 more characters; call again with start=22
    >>> read_document("dsid_zz", docs)
    'No document with id dsid_zz'
"""
from collections import OrderedDict
from pathlib import Path
from typing import Collection, Dict, List, Optional, Sequence, Tuple, Union

from llama_index.core.schema import NodeWithScore

from pipeline.eval.answers import documents_by_id

DOCUMENTS_PER_SEARCH = 10  # as the benchmark's baseline answerer and GEN-2a
SNIPPETS_PER_DOCUMENT = 2  # a second snippet shows a document that matched in two places
SNIPPET_CHARS = 400  # one or two sentences: enough to decide whether to read; the full chunk is ~2,350
NO_TITLE = ("?", "(no title)")  # a doc_id the title table does not know: the agent may mistype one
READ_CHARS = 30_000  # above the p99 of 11,846: only the 22 longest Fireflies transcripts are windowed


def snippet_of(text: str, title: str, chars: int) -> str:
    """The chunk's content in one line: the leading title line dropped, cut to `chars` with an ellipsis."""
    after_title = text[len(title):] if title and text.startswith(title) else None
    body = after_title.lstrip(" \n:") if after_title is not None and after_title[:1] in ("", "\n", ":") else text  # a title line, not a word prefix ("incidents" vs "incidents-bot: …")
    body = " ".join(body.split())
    return body if len(body) <= chars else body[:chars] + "…"


def chunks_by_document(ranked: Sequence[NodeWithScore], titles: Dict[str, Tuple[str, str]], source: Optional[str] = None,
                       documents: int = DOCUMENTS_PER_SEARCH) -> "OrderedDict[str, List[Tuple[int, str]]]":
    """The first `documents` documents of `source` in best-chunk order, each with its (rank, text) chunks."""
    by_document: "OrderedDict[str, List[Tuple[int, str]]]" = OrderedDict()
    for rank, chunk in enumerate(ranked, 1):
        doc_id = chunk.node.ref_doc_id
        if source is None or titles.get(doc_id, NO_TITLE)[0] == source:
            by_document.setdefault(doc_id, []).append((rank, chunk.node.text))
    return OrderedDict(list(by_document.items())[:documents])


def search_snippets(ranked: Sequence[NodeWithScore], titles: Dict[str, Tuple[str, str]], source: Optional[str] = None,
                    read: Collection[str] = (), seen: Collection[str] = (), documents: int = DOCUMENTS_PER_SEARCH,
                    per_document: int = SNIPPETS_PER_DOCUMENT, snippet_chars: int = SNIPPET_CHARS) -> str:
    """One block per document, in best-chunk order, at most `documents`; `titles` maps doc_id to (source, title)."""
    blocks = []
    for number, (doc_id, chunks) in enumerate(chunks_by_document(ranked, titles, source, documents).items(), 1):
        doc_source, title = titles.get(doc_id, NO_TITLE)
        shown = chunks[:per_document]
        marker = " (read)" if doc_id in read else " (seen)" if doc_id in seen else ""  # read wins: it says more
        head = (f"[{number}] {title} | {doc_source} | {doc_id} | {len(chunks)} chunk{'s' if len(chunks) != 1 else ''} matched, "
                f"{len(shown)} shown{marker}")
        blocks.append("\n".join([head] + [f"  (rank {rank}) {snippet_of(text, title, snippet_chars)}" for rank, text in shown]))
    return "\n".join(blocks) if blocks else "No documents matched."


def read_document(doc_id: str, documents: Dict[str, Tuple[str, str]], parquet_path: Optional[Union[str, Path]] = None,
                  start: int = 0, chars: int = READ_CHARS) -> str:
    """The title as a heading and the content from `start`, whole if it fits in `chars`, else cut at a line break with a note.

    `documents` is `{doc_id: (title, content)}` and is the cache: a miss read from `parquet_path` is added to it.
    """
    if doc_id not in documents and parquet_path is not None:
        documents.update(documents_by_id(parquet_path, [doc_id]))  # one scan of the corpus, then cached
    if doc_id not in documents:
        return f"No document with id {doc_id}"
    title, content = documents[doc_id]
    start = max(start, 0)
    if start and start >= len(content):  # an empty document still shows its title
        return f"{doc_id} has {len(content)} characters; nothing after {start}"
    heading = f"# {title or doc_id}\n\n"
    if len(content) - start <= chars:
        return heading + content[start:]
    end = content.rfind("\n", start, start + chars)
    if end <= start:  # no line break inside the window (or only at its start): hard cut
        end = next_start = start + chars
    else:
        next_start = end + 1  # skip the newline
    return f"{heading}{content[start:end]}\n\n… {len(content) - next_start:,} more characters; call again with start={next_start}"

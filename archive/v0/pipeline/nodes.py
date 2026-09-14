"""LlamaIndex integration: clean Confluence files -> Documents -> section-aware TextNodes.

Parsing is markdown-it-py (native headings, lists, tables, fenced code, with source line
maps) plus the plain-label heading rule from pipeline.structure for bucket C/D files.
Lists, tables and code fences are never split. Each node carries the document title and
section breadcrumb in its text and exact source line range in its metadata.

Usage:
    from pipeline.nodes import load_documents, ConfluenceNodeParser
    docs = load_documents()                       # data/confluence/clean
    nodes = ConfluenceNodeParser().get_nodes_from_documents(docs)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from llama_index.core.node_parser import NodeParser
from llama_index.core.schema import BaseNode, Document, NodeRelationship, TextNode
from markdown_it import MarkdownIt

from pipeline.structure import bucket, label_flags

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data/confluence/clean"
_MD = MarkdownIt("commonmark").enable("table")

ATOMIC = {"bullet_list_open", "ordered_list_open", "table_open", "fence", "code_block", "blockquote_open", "html_block"}


def load_documents(clean_dir: Path = CLEAN_DIR) -> list[Document]:
    """One Document per clean file, with triage/manifest metadata attached."""
    manifest = {m["file"]: m for m in json.loads((clean_dir / "_manifest.json").read_text())} if (clean_dir / "_manifest.json").exists() else {}
    triage = {t["file"]: t for t in json.loads((clean_dir / "_triage.json").read_text())} if (clean_dir / "_triage.json").exists() else {}
    docs = []
    for path in sorted(clean_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        m, t = manifest.get(path.name, {}), triage.get(path.name, {})
        docs.append(Document(
            id_=path.name.split("__", 1)[0],
            text=text,
            metadata={
                "source_path": str(path.relative_to(ROOT)),
                "title": text.splitlines()[0].strip() if text.strip() else "",
                "bucket": t.get("bucket") or bucket(text),
                "needs_review": t.get("needs_review", False),
                "flags": t.get("flags", []),
                "clean_sha256": m.get("clean_sha256"),
                "raw_sha256": m.get("raw_sha256"),
            },
            excluded_embed_metadata_keys=["source_path", "clean_sha256", "raw_sha256", "flags", "needs_review", "bucket"],
            excluded_llm_metadata_keys=["clean_sha256", "raw_sha256", "flags", "needs_review", "bucket"],
        ))
    return docs


def _blocks(text: str) -> list[dict]:
    """Top-level blocks with [start, end) line ranges; paragraphs split off leading label lines."""
    lines = text.splitlines()
    use_labels = bucket(text) in ("C_plain_labels", "D_prose")
    flags = label_flags(lines) if use_labels else [False] * len(lines)
    if lines and lines[0].strip():
        flags[0] = True  # title line is always a heading, in every bucket
    tokens = _MD.parse(text)
    out: list[dict] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.level != 0 or not tok.map or tok.type.endswith("_close"):
            i += 1; continue
        start, end = tok.map
        if tok.type == "heading_open":
            out.append({"kind": "heading", "level": int(tok.tag[1]), "text": tokens[i + 1].content.strip(), "start": start, "end": end, "native": True})
        elif tok.type == "paragraph_open":
            j = start
            while j < end and flags[j]:
                out.append({"kind": "heading", "level": 1 if j == 0 else 2, "text": lines[j].strip(), "start": j, "end": j + 1, "native": False}); j += 1
            if j < end:
                out.append({"kind": "text", "start": j, "end": end})
        else:
            out.append({"kind": "atomic" if tok.type in ATOMIC else "text", "start": start, "end": end, "type": tok.type})
        i += 1
    return out


class ConfluenceNodeParser(NodeParser):
    """Section-aware chunker: split on headings, pack blocks up to max_chars, never split atomic blocks."""

    max_chars: int = 1600
    include_breadcrumb: bool = True

    @classmethod
    def class_name(cls) -> str:
        return "ConfluenceNodeParser"

    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> list[BaseNode]:
        out: list[BaseNode] = []
        for doc in nodes:
            out.extend(self._chunk_document(doc))
        return out

    def _chunk_document(self, doc: BaseNode) -> list[TextNode]:
        text = doc.get_content()
        lines = text.splitlines()
        title = doc.metadata.get("title") or (lines[0].strip() if lines else "")
        stack: list[tuple[int, str]] = []  # (level, heading)
        pending: list[dict] = []
        pending_chars = 0
        result: list[TextNode] = []
        chunk_index = 0

        def flush():
            nonlocal pending, pending_chars, chunk_index
            if not pending: return
            start, end = pending[0]["start"], pending[-1]["end"]
            body = "\n".join(lines[start:end]).strip("\n")
            crumb = [h for _, h in stack]
            header = " > ".join([title] + [c for c in crumb if c != title]) if self.include_breadcrumb else ""
            node = TextNode(
                text=(header + "\n\n" + body) if header else body,
                metadata={**doc.metadata, "heading": crumb[-1] if crumb else title, "heading_path": crumb,
                          "line_start": start + 1, "line_end": end, "chunk_index": chunk_index,
                          "block_types": sorted({b.get("type", b["kind"]) for b in pending})},
                excluded_embed_metadata_keys=list(doc.excluded_embed_metadata_keys) + ["line_start", "line_end", "chunk_index", "block_types", "heading_path"],
                excluded_llm_metadata_keys=list(doc.excluded_llm_metadata_keys) + ["chunk_index", "block_types"],
            )
            node.relationships[NodeRelationship.SOURCE] = doc.as_related_node_info()
            result.append(node); chunk_index += 1
            pending, pending_chars = [], 0

        last_heading_empty = False
        for b in _blocks(text):
            if b["kind"] == "heading":
                flush()
                level = b["level"]
                # A label with no content of its own is a parent: nest the next label under it.
                if not b["native"] and last_heading_empty and stack and level <= stack[-1][0]:
                    level = stack[-1][0] + 1
                while stack and stack[-1][0] >= level: stack.pop()
                stack.append((level, b["text"]))
                last_heading_empty = True
                continue
            last_heading_empty = False
            size = sum(len(lines[k]) + 1 for k in range(b["start"], b["end"]))
            if pending and pending_chars + size > self.max_chars:
                flush()
            pending.append(b); pending_chars += size
        flush()
        for k, n in enumerate(result):
            if k: n.relationships[NodeRelationship.PREVIOUS] = result[k - 1].as_related_node_info()
            if k + 1 < len(result): n.relationships[NodeRelationship.NEXT] = result[k + 1].as_related_node_info()
        return result


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests/fixtures/typical.md"
    text = path.read_text()
    doc = Document(id_=path.stem, text=text, metadata={"title": text.splitlines()[0]})
    for n in ConfluenceNodeParser().get_nodes_from_documents([doc]):
        m = n.metadata
        print(f"[{m['chunk_index']:2d}] L{m['line_start']}-{m['line_end']} {len(n.text):4d}ch  {' > '.join(m['heading_path'])[:70]}  {m['block_types']}")

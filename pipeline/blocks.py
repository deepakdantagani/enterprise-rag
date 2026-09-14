"""PARSE-7: the top-level blocks of a clean file, as markdown-it sees them.

Headings say where a section starts; blocks say what must not be cut in half: a
list, a table, a code fence. This module reads block boundaries out of markdown-it.

Real example, the "Audience:" list in the scheduler file:

    6  Audience:
    7  - Oncall SREs and runtime engineers
    8  - Kernel and scheduler owners
    9  - Runtime observability and automation engineers
    10
    11 Why SHO: problem statement

    markdown-it token: type="bullet_list_open", map=[7, 11)
    ours:              Block(kind="list", start=7, end=11)     4 lines, end exclusive

Pure module.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    """One top-level block: what it is and which lines it covers, [start, end).

    >>> b = Block(kind="list", start=7, end=11)
    >>> b.kind, b.start, b.end, b.lines
    ('list', 7, 11, 4)
    """
    kind: str    # one of the eight values in KIND_OF_TOKEN
    start: int   # first line, 0-based
    end: int     # one past the last line; for lists may include the trailing blank

    @property
    def lines(self) -> int:
        return self.end - self.start


# markdown-it token type -> our kind. Every top-level token type seen in the corpus.
KIND_OF_TOKEN = {
    "paragraph_open": "text",
    "bullet_list_open": "list",
    "ordered_list_open": "list",
    "heading_open": "heading",
    "hr": "rule",
    "table_open": "table",
    "fence": "code",
    "code_block": "code",
    "blockquote_open": "quote",
    "html_block": "html",
}

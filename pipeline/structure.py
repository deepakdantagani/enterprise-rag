"""PARSE-8a: what markdown-it sees in one clean file.

Three facts from one parse, all as 0-based line numbers of the clean file:

  headings    line -> level, for `#` headings and underlined headings
  underlines  the `---` / `===` lines of the underlined headings
  protected   [start, end) ranges of code fences and tables

`to_markdown` keeps the headings, blanks the underlines, and never writes a `#` inside
a protected range. markdown-it does the parsing; the only rules of our own are the two
guards below, each backed by a count on the corpus (docs/stories/2-chunking.md).

>>> structure("Summary\\n-------\\ntext")
Structure(headings={0: 2}, underlines={1}, protected=[])
"""
from dataclasses import dataclass

from pipeline.markdown import MARKDOWN

PROTECTED_TOKENS = ("fence", "table_open")


@dataclass(frozen=True)
class Structure:
    headings: dict[int, int]
    underlines: set[int]
    protected: list[tuple[int, int]]


def structure(text: str) -> Structure:
    headings: dict[int, int] = {}
    underlines: set[int] = set()
    protected: list[tuple[int, int]] = []

    for token in MARKDOWN.parse(text):
        if token.type in PROTECTED_TOKENS:
            protected.append((token.map[0], token.map[1]))
        elif token.type == "heading_open" and is_top_level(token):
            start, end = token.map
            underlined = token.markup[0] in "-="
            if underlined and not is_one_line_of_text(start, end):
                continue
            headings[start] = int(token.tag[1])
            if underlined:
                underlines.add(end - 1)

    return Structure(headings, underlines, protected)


def is_top_level(token) -> bool:
    """A heading nested in a list or quote is not a section: `- p95 latency:` over
    `  -` parses as one, 216 times in the corpus, never a real heading."""
    return token.level == 0


def is_one_line_of_text(start: int, end: int) -> bool:
    """An underlined heading is one text line plus its underline. A `---` under a longer
    paragraph closes a YAML block (191 times in the corpus), it does not make a heading."""
    return end - start == 2

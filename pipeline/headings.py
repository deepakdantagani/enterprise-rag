"""PARSE-5: one data shape for headings, whoever finds them.

The chunker (PARSE-8) asks a HeadingDetector for the headings of a file and never
learns whether they came from Markdown markup (MarkdownHeadings, 5b) or from the
plain-label rule (LabelHeadings, PARSE-6).

Real example, the first lines of a bucket B file:

    0  Fallback validation and chaos test plan for graceful runtime fallbacks
    1
    2  Purpose
    3  -------

    find_headings -> [Heading(line=0, level=1, text="Fallback validation ..."),
                      Heading(line=2, level=2, text="Purpose")]

Line 3, the underline, is markup and produces no Heading.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pipeline.buckets import bucket
from pipeline.label_rule import label_flags
from pipeline.markdown import MARKDOWN


@dataclass(frozen=True)
class Heading:
    """One heading: where it is, how deep it is, what it says.

    >>> h = Heading(line=2, level=2, text="Purpose")
    >>> h.line, h.level, h.text
    (2, 2, 'Purpose')
    >>> h == Heading(2, 2, "Purpose")
    True
    """
    line: int    # 0-based index into the file's lines
    level: int   # 1 = document title, 2 and deeper = sections
    text: str    # heading text without markup, stripped


@runtime_checkable
class HeadingDetector(Protocol):
    """Anything with find_headings(lines) -> list[Heading], sorted by line."""

    def find_headings(self, lines: list[str]) -> list[Heading]: ...


class MarkdownHeadings:
    """Headings written in Markdown ("# Scope", or "Scope" over "-----"), plus the title line.

    >>> MarkdownHeadings().find_headings(["Title", "", "## Scope", "text"])
    [Heading(line=0, level=1, text='Title'), Heading(line=2, level=2, text='Scope')]
    """

    def find_headings(self, lines: list[str]) -> list[Heading]:
        return with_title(lines, markdown_headings(lines))


def markdown_headings(lines: list[str]) -> list[Heading]:
    """Every top-level heading token markdown-it finds, in line order.

    A heading is a `heading_open` token at nesting level 0 with a line map; its text is
    the next token's content. A "#" inside a code fence is not a token at all, and one
    inside a blockquote or list is nested (level > 0) and skipped.

    Input -> output:
        >>> markdown_headings(["## Scope", "text"])
        [Heading(line=0, level=2, text='Scope')]
        >>> markdown_headings(["Scope", "-----", "text"])      # setext: the underline is not reported
        [Heading(line=0, level=2, text='Scope')]

    Edge cases:
        >>> markdown_headings(["```", "# code", "```"]), markdown_headings(["> # quoted"])
        ([], [])
    """
    tokens = MARKDOWN.parse("\n".join(lines))
    found = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.level == 0 and token.map:
            found.append(Heading(line=token.map[0],
                                 level=int(token.tag[1]),          # "h2" -> 2
                                 text=tokens[i + 1].content.strip()))
    return found


def with_title(lines: list[str], found: list[Heading]) -> list[Heading]:
    """Line 0, when non-blank, is the level-1 title unless a heading was already found there.

    Input -> output:
        >>> with_title(["Title", "", "## Scope"], [Heading(2, 2, "Scope")])
        [Heading(line=0, level=1, text='Title'), Heading(line=2, level=2, text='Scope')]
        >>> with_title(["# Title"], [Heading(0, 1, "Title")])          # already reported
        [Heading(line=0, level=1, text='Title')]

    Edge cases:
        >>> with_title([], []), with_title([""], [])
        ([], [])
    """
    if not lines or not lines[0].strip():
        return found
    if found and found[0].line == 0:
        return found
    return [Heading(line=0, level=1, text=lines[0].strip())] + found


class LabelHeadings:
    """Headings found by the plain-label rule (PARSE-4), for files with no Markdown headings.

    One Heading per True flag. Line 0 is the level-1 title (label_flags applies the
    title rule itself); every other label is level 2, the rule has no notion of depth.

    >>> LabelHeadings().find_headings(["Title", "", "Overview", "", "Body."])
    [Heading(line=0, level=1, text='Title'), Heading(line=2, level=2, text='Overview')]
    >>> LabelHeadings().find_headings(["", "Label"])      # blank line 0: no title
    [Heading(line=1, level=2, text='Label')]
    """

    def find_headings(self, lines: list[str]) -> list[Heading]:
        flags = label_flags(lines)
        return [Heading(line=i, level=1 if i == 0 else 2, text=lines[i].strip())
                for i, is_label in enumerate(flags) if is_label]


def detector_for(text: str) -> HeadingDetector:
    """Pick the detector for one clean file: Markdown for buckets A/B, the label rule for C/D.

    The chunker calls this and never sees bucket names.

    >>> type(detector_for("# Title\\n\\ntext")).__name__
    'MarkdownHeadings'
    >>> type(detector_for("Overview\\n\\n- item")).__name__
    'LabelHeadings'
    """
    if bucket(text) in ("A_hash", "B_setext"):
        return MarkdownHeadings()
    return LabelHeadings()

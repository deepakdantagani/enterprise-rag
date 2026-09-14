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

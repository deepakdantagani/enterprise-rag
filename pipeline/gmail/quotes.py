"""GMAIL-6: remove the quoted earlier email from a message body.

A quote is every line that starts with ">" plus the "On ... wrote:" line above it (which may end
in a leftover literal \\r or a short note in brackets, or carry the quote on the same line). Text the
author wrote around or between quoted lines stays, and so do forwarded messages and quoted
history with no ">" marks: those cannot be told apart from new text. The clean file on disk
is not touched; only the returned text loses the quote. The remaining text is always tidied
(trailing spaces, runs of blank lines), whether or not a quote was found.
"""
import re
from dataclasses import dataclass

from pipeline.gmail.cleaning import tidy_whitespace

QUOTE_MARK = ">"
OPENER = re.compile(r"^On .{5,200} wrote:(?:\s*(?:\\r|\([^)]{0,40}\)))?\s*$")
QUOTE_ON_OPENER_LINE = re.compile(r"^On .{5,200} wrote:\s*>(?:\s|$)")


@dataclass(frozen=True)
class StrippedBody:
    text: str
    quoted_chars: int
    opener_unmatched: bool


def strip_quotes(body: str) -> StrippedBody:
    lines = body.split("\n")
    quoted, opener_unmatched = find_quoted_lines(lines)
    kept = "\n".join(line for number, line in enumerate(lines) if number not in quoted)
    quoted_chars = sum(len(lines[number]) + 1 for number in quoted)
    return StrippedBody(tidy_whitespace(kept).strip("\n"), quoted_chars, opener_unmatched)


def find_quoted_lines(lines: list[str]) -> tuple[set[int], bool]:
    """Line numbers to remove, and whether some "On ... wrote:" line has no quote after it."""
    quoted: set[int] = set()
    opener_unmatched = False
    for number, line in enumerate(lines):
        if line.startswith(QUOTE_MARK) or QUOTE_ON_OPENER_LINE.match(line):
            quoted.add(number)
        elif OPENER.match(line):
            if first_line_after(lines, number).startswith(QUOTE_MARK):
                quoted.add(number)
            else:
                opener_unmatched = True
    return quoted, opener_unmatched


def first_line_after(lines: list[str], number: int) -> str:
    """The next line, skipping at most one blank line; empty when there is none."""
    following = lines[number + 1 : number + 3]
    if following and not following[0].strip():
        following = following[1:]
    return following[0] if following else ""

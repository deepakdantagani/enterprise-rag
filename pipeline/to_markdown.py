"""PARSE-8b: every clean file becomes Markdown, one pass per file.

8b1  label_lines   which label-rule lines are sections of this page
8b2  to_markdown   writes the `#`s (next story)

Each rule in `label_lines` is a decision recorded with its evidence in
docs/stories/2-chunking.md and tested against the PARSE-17 truth set.
"""
import re

from pipeline.label_rule import label_flags
from pipeline.structure import Structure

TITLE_LINE = 0
QUESTION = re.compile(r"^Q\d*[:.)]\s")


def label_lines(lines: list[str], found: Structure) -> set[int]:
    """The label-rule lines that a reader would call a section heading.

    >>> from pipeline.structure import structure
    >>> text = "Title\\n\\nFAQs:\\nQ: Why?\\nA: Because."
    >>> sorted(label_lines(text.split("\\n"), structure(text)))
    [2]
    """
    protected = {line for start, end in found.protected for line in range(start, end)}
    labels = {
        line
        for line, flagged in enumerate(label_flags(lines))
        if flagged
        and line != TITLE_LINE
        and line not in protected
        and line not in found.headings
        and not is_question(lines[line])
    }
    if not labels_are_the_majority_style(labels, found):
        return set()
    headings = labels | set(found.headings) | {TITLE_LINE}
    return {line for line in labels if line - 1 not in headings}


def is_question(line: str) -> bool:
    """`Q: Why?` belongs to its FAQ: a whole FAQ is one context and fits one chunk."""
    return bool(QUESTION.match(line.strip()))


def labels_are_the_majority_style(labels: set[int], found: Structure) -> bool:
    """The author's main heading style marks the sections. On a page written in `##`,
    a bare label or bold line is a lead-in; a tie goes to the Markdown the author wrote."""
    return len(labels) > len(found.headings)

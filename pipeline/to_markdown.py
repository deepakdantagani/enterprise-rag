"""PARSE-8b: every clean file becomes Markdown, one pass per file.

8b1  label_lines   which label-rule lines are sections of this page
8b2  to_markdown   writes the `#`s, same line count, so "line 12" means the same
                   line in the raw, clean and Markdown copies of a page
8c   heading_lines the headings of a Markdown copy as LlamaIndex will find them

Each rule in `label_lines` is a decision recorded with its evidence in
docs/stories/2-chunking.md and tested against the PARSE-17 truth set.
"""
import re

from pipeline.label_rule import label_flags
from pipeline.structure import Structure, structure

TITLE_LINE = 0
TITLE_LEVEL = 1
LABEL_LEVEL = 2
QUESTION = re.compile(r"^Q\d*[:.)]\s")
HASH_HEADING = re.compile(r"^#{1,6}\s")


def to_markdown(text: str) -> str:
    """The clean text with `#`s on every heading line; every other line untouched.

    >>> to_markdown("Deploy guide\\n\\nRollback\\n--------\\nSteps here.")
    '# Deploy guide\\n\\n## Rollback\\n\\nSteps here.'
    """
    lines = text.split("\n")
    found = structure(text)

    levels = {line: LABEL_LEVEL for line in label_lines(lines, found)}
    levels |= {line: level for line, level in found.headings.items() if line + 1 in found.underlines}
    if TITLE_LINE not in found.headings and lines[TITLE_LINE].strip():
        levels[TITLE_LINE] = TITLE_LEVEL

    for line, level in levels.items():
        lines[line] = "#" * level + " " + lines[line].strip()
    for line in found.underlines:
        lines[line] = ""
    return "\n".join(lines)


def heading_lines(markdown: str) -> set[int]:
    """The heading lines as LlamaIndex's MarkdownNodeParser finds them: `#`s at the start
    of a line, outside code fences. A page with only line 0 here has no sections.

    >>> sorted(heading_lines("# T\\n\\n```\\n# not one\\n```\\n## A"))
    [0, 5]
    """
    fenced = {line for start, end in structure(markdown).protected for line in range(start, end)}
    return {n for n, line in enumerate(markdown.split("\n")) if HASH_HEADING.match(line) and n not in fenced}


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

r"""PARSE-3: which markup style does a clean file use?

Four buckets, strongest signal wins, checked in this order:

    A_hash          at least one "# Heading" line              1,645 files
    B_setext        a short line over "=====" or "-----"          781 files
    C_plain_labels  no headings, but lists, tables or fences    2,751 files
    D_prose         none of the above, or empty                    12 files

The chunker uses the bucket to pick a heading detector (PARSE-5, PARSE-6).
Pure module: it is handed the clean text and returns one string.
"""
import re

HASH_HEADING = re.compile(r"^#{1,6} ", re.M)                        # "## Scope"
SETEXT_HEADING = re.compile(r"^[^\n]{1,80}\n(=+|-{3,})\s*$", re.M)  # "Scope" over "-----"
LIST_TABLE_OR_FENCE = re.compile(r"^\s*([-*+]|\d+[.)]) |^\||^```", re.M)


def bucket(text: str) -> str:
    r"""Classify a clean file by the strongest structure signal it carries.

    Input -> output:
        >>> bucket("# Title\n\ntext")
        'A_hash'
        >>> bucket("Title\n-----\n\ntext")
        'B_setext'
        >>> bucket("Overview\n\n- item")
        'C_plain_labels'
        >>> bucket("Just prose.\n\nMore prose.")
        'D_prose'

    Edge cases:
        >>> bucket("")
        'D_prose'
        >>> bucket("Intro\n-----\n\n# Real\n\n- item")    # "#" wins when both are present
        'A_hash'
    """
    if HASH_HEADING.search(text):
        return "A_hash"
    if SETEXT_HEADING.search(text):
        return "B_setext"
    if LIST_TABLE_OR_FENCE.search(text):
        return "C_plain_labels"
    return "D_prose"

r"""PARSE-1. The text cleaning rules. Pure functions: string in, string out, no files.

Entry point:  clean_text(raw) -> CleanResult(text, was_escaped)

Why this module exists
----------------------
Raw Confluence exports are inconsistent. About one file in five has its whole body on
one line with "\n" written as two characters (it was JSON-string encoded on the way
out). Some carry Confluence wiki markup. Some have tables missing the separator row
that Markdown needs. Each of those confuses the Markdown parser, so we fix them here.

Example:
    raw:    'Title\n\nSummary:\\n\\n- one\\n- two'
    clean:  'Title\n\nSummary:\n\n- one\n- two\n'

The three rules, in the order they run
--------------------------------------
1. unescape()        JSON-style escapes -> real characters (only when is_escaped says so)
2. fix_structure()   wiki headings, wiki tables, numbered setext headings, table separators
3. normalize()       trailing spaces, extra blank lines, exactly one final newline

Conventions: every function shows "Input -> output" and "Edge cases" doctests, run by
tests/test_cleaning.py. Trivial cases return early.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CleanResult:
    text: str
    was_escaped: bool


def clean_text(raw: str) -> CleanResult:
    r"""Run the three rules on one document's text.

    Input -> output:
        >>> clean_text("Title\n\nA:\\n- x\\n- y\\n- z\\n- w\\n")
        CleanResult(text='Title\n\nA:\n- x\n- y\n- z\n- w\n', was_escaped=True)
        >>> clean_text("Title\n\nBody.\n")
        CleanResult(text='Title\n\nBody.\n', was_escaped=False)

    Edge cases:
        >>> clean_text("")
        CleanResult(text='', was_escaped=False)
    """
    escaped = is_escaped(raw)
    text = unescape(raw) if escaped else raw
    return CleanResult(text=normalize(text), was_escaped=escaped)


# ---------------------------------------------------------------------------
# Rule 1: JSON-style escapes
# ---------------------------------------------------------------------------

def is_escaped(text: str) -> bool:
    r"""True when newlines appear as the two characters backslash + n.

    We compare counts rather than looking for any "\n" at all: a normal file can hold a
    few (a printf string, a jsonpath). An escaped file has far more literal "\n" than
    real newlines. Real newlines can still exist inside its code fences.

    Input -> output:
        >>> is_escaped("Title\\n\\nSummary:\\n- a\\n- b\\n- c\\n")   # 6 literal, 0 real
        True
        >>> is_escaped("Title\n\nprintf('%s\\n')\nmore\nlines\n")       # 1 literal, 5 real
        False

    Edge cases:
        >>> is_escaped("")
        False
    """
    literal_newlines = text.count("\\n")
    if literal_newlines < 5:
        return False  # too few to be an encoded body
    real_newlines = text.count("\n")
    return literal_newlines > real_newlines


_BACKSLASH_PLACEHOLDER = "\x00BS\x00"  # never occurs in the corpus


def unescape(text: str) -> str:
    r"""Turn JSON-style escapes back into characters: \n \t \" \\ \uXXXX.

    Order matters. "\\" means one real backslash and must not be confused with the
    backslash that starts "\n". So real backslashes are parked in a placeholder first,
    everything else is unescaped, then the backslashes are put back.

    Input -> output:
        >>> unescape('Say \\"hi\\"\\n\\tindented\\ncaf\\u00e9 and a\\\\b')
        'Say "hi"\n\tindented\ncafé and a\\b'

    Edge cases:
        >>> unescape("")
        ''
        >>> unescape("no escapes here")
        'no escapes here'
    """
    if "\\" not in text:
        return text
    text = text.replace("\\\\", _BACKSLASH_PLACEHOLDER)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", _unicode_escape_to_char, text)
    text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")
    text = text.replace('\\"', '"')
    text = text.replace(_BACKSLASH_PLACEHOLDER, "\\")
    return text


def _unicode_escape_to_char(match: re.Match) -> str:
    r"""'é' -> 'é'"""
    return chr(int(match.group(1), 16))


# ---------------------------------------------------------------------------
# Rule 2: structure fixes, so the Markdown parser sees what a human sees
# ---------------------------------------------------------------------------

WIKI_HEADING = re.compile(r"^h([1-6])\. (.+)$")                  # "h2. Scope"
WIKI_TABLE_ROW = re.compile(r"^\|\|.*\|\|\s*$")                    # "||Name||Owner||"
TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|\s*$")                 # "|---|---:|"
SETEXT_UNDERLINE = re.compile(r"^(-{3,}|=+)\s*$")                  # "-----" or "====="
LIST_ITEM_START = re.compile(r"^\s*(\d+[.)]|[a-z][.)]|[-*+]) ")    # "1) ", "a. ", "- "


def fix_structure(lines: list[str]) -> list[str]:
    """Walk the lines and rewrite the few shapes that confuse CommonMark.

    Input -> output (one example of each rewrite):
        >>> fix_structure(["h2. Scope"])
        ['## Scope']
        >>> fix_structure(["||Name||Owner||", "| api | Ana |"])
        ['| Name | Owner |', '|---|---|', '| api | Ana |']
        >>> fix_structure(["1) Access", "---------", "Body"])
        ['## 1) Access', 'Body']
        >>> fix_structure(["| A | B |", "| 1 | 2 |"])
        ['| A | B |', '|---|---|', '| 1 | 2 |']

    Edge cases:
        >>> fix_structure([])
        []
        >>> fix_structure(["| a lone pipe line |"])        # one row is not a table
        ['| a lone pipe line |']
        >>> fix_structure(["Title", "-----"])                # a normal setext heading: Markdown handles it
        ['Title', '-----']
    """
    if not lines:
        return []
    fixed = []
    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        previous_line = lines[i - 1] if i > 0 else ""

        if _is_wiki_heading(line):
            fixed.append(_wiki_heading_to_markdown(line))
            i += 1
        elif _is_wiki_table_row(line):
            header_row, separator_row = _wiki_table_row_to_markdown(line)
            fixed.extend([header_row, separator_row])
            i += 1
        elif _is_numbered_setext_heading(line, next_line):
            fixed.append(_setext_to_atx_heading(line, next_line))
            i += 2  # the underline is consumed too
        elif _is_table_header_without_separator(line, previous_line, next_line):
            fixed.extend([line, _separator_row_for(line)])
            i += 1
        else:
            fixed.append(line)
            i += 1
    return fixed


def _is_wiki_heading(line: str) -> bool:
    return WIKI_HEADING.match(line) is not None


def _wiki_heading_to_markdown(line: str) -> str:
    """
        >>> _wiki_heading_to_markdown("h3. Rollout plan")
        '### Rollout plan'
    """
    level, title = WIKI_HEADING.match(line).groups()
    return "#" * int(level) + " " + title.strip()


def _is_wiki_table_row(line: str) -> bool:
    return WIKI_TABLE_ROW.match(line) is not None


def _wiki_table_row_to_markdown(line: str) -> tuple[str, str]:
    """
        >>> _wiki_table_row_to_markdown("||a||b||")
        ('| a | b |', '|---|---|')
    """
    cells = [cell.strip() for cell in line.strip().strip("|").split("||")]
    return "| " + " | ".join(cells) + " |", "|" + "---|" * len(cells)


def _is_numbered_setext_heading(line: str, next_line: str) -> bool:
    """A heading written as a list-looking line with an underline:
        1) Access & Permissions
        ----------------------
    CommonMark reads the first line as a list item and the underline as a rule, so the
    heading is lost. We rewrite it to '## 1) Access & Permissions'.

        >>> _is_numbered_setext_heading("1) Access & Permissions", "----------------------")
        True
        >>> _is_numbered_setext_heading("1) A normal list item", "2) Another item")
        False
    """
    return bool(line.strip()) and LIST_ITEM_START.match(line) is not None and SETEXT_UNDERLINE.match(next_line) is not None


def _setext_to_atx_heading(line: str, underline: str) -> str:
    """
        >>> _setext_to_atx_heading("1) Access", "---------")
        '## 1) Access'
        >>> _setext_to_atx_heading("1. Intro", "========")
        '# 1. Intro'
    """
    level = 1 if underline.startswith("=") else 2
    return "#" * level + " " + line.strip()


def _is_table_header_without_separator(line: str, previous_line: str, next_line: str) -> bool:
    """First row of a pipe table whose second row is data, not '|---|'. Without the
    separator Markdown does not see a table at all.

        >>> _is_table_header_without_separator("| A | B |", "text above", "| 1 | 2 |")
        True
        >>> _is_table_header_without_separator("| A | B |", "text above", "|---|---|")
        False
        >>> _is_table_header_without_separator("| 1 | 2 |", "| A | B |", "| 3 | 4 |")   # not the first row
        False
    """
    starts_a_pipe_run = line.startswith("|") and not previous_line.startswith("|")
    next_is_data_row = next_line.startswith("|") and TABLE_SEPARATOR.match(next_line) is None
    return starts_a_pipe_run and next_is_data_row


def _separator_row_for(header_row: str) -> str:
    """
        >>> _separator_row_for("| A | B | C |")
        '|---|---|---|'
    """
    column_count = len(header_row.strip().strip("|").split("|"))
    return "|" + "---|" * column_count


# ---------------------------------------------------------------------------
# Rule 3: whitespace
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    r"""Apply the structure fixes, then tidy whitespace: no trailing spaces, at most one
    blank line in a row, exactly one final newline.

    Input -> output:
        >>> normalize("Title   \n\n\n\nBody\n\n\n")
        'Title\n\nBody\n'

    Edge cases:
        >>> normalize("")
        ''
        >>> normalize("Title")            # no final newline in the source: one is added
        'Title\n'
    """
    if not text.strip():
        return ""
    lines = fix_structure([line.rstrip() for line in text.splitlines()])
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"

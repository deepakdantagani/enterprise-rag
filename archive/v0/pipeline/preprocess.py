"""Step 1 of the pipeline: turn a raw Confluence export into clean, well-formed text.

What goes in:   data/confluence/raw/<doc>.txt   (exactly as exported)
What comes out: data/confluence/clean/<doc>.txt  (same content, tidied)
                data/confluence/clean/_manifest.json  (sha256 of raw and clean, per file)

Run:  uv run python -m pipeline.preprocess

Why this step exists
--------------------
The exports are not consistent. About one file in five has its whole body on one
line with "\\n" written as two characters, because it was JSON-string encoded on the
way out. Some files still carry Confluence wiki markup. Some have tables missing the
separator row that Markdown needs. Each of those trips up the parser in step 2, so we
fix them here, once, and never touch the raw files.

Example: raw file
    Title
    <blank>
    Summary:\\n\\n- one\\n- two
becomes
    Title
    <blank>
    Summary:
    <blank>
    - one
    - two

The rules, in the order they run
--------------------------------
1. unescape()        JSON-style escapes -> real characters (only when the file is escaped)
2. fix_structure()   wiki headings, wiki tables, numbered setext headings, missing table separators
3. normalize()       trailing spaces, extra blank lines, final newline

Conventions used in this file
-----------------------------
- Every function that changes data shows "Input -> output" and "Edge cases" examples in
  its docstring. They are real doctests, run by tests/test_pipeline.py.
- Functions return early on the trivial case (empty input, nothing to do) so the main
  path below the guard is the interesting part.
- Raw files are never modified; everything is written to the clean folder.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/confluence/raw"
CLEAN_DIR = ROOT / "data/confluence/clean"


# ---------------------------------------------------------------------------
# Rule 1: JSON-style escapes
# ---------------------------------------------------------------------------

def is_escaped(text: str) -> bool:
    r"""True when the body was JSON-string encoded, i.e. newlines appear as the two
    characters backslash + n.

    We compare counts rather than looking for any "\\n" at all, because a normal file
    can legitimately contain a few, for example inside a printf string. An escaped
    file has far more literal "\\n" than real newlines; a normal file has the reverse.

    Input -> output:
        >>> is_escaped("Title\\n\\nSummary:\\n- a\\n- b\\n- c\\n")   # one real line, six literal \\n
        True
        >>> is_escaped("Title\n\nprintf('%s\\n')\nmore\nlines\n")          # a real file with one literal \\n
        False

    Edge cases:
        >>> is_escaped("")
        False
    """
    literal_newlines = text.count("\\n")
    if literal_newlines < 5:
        return False  # too few to be an encoded body; could be printf strings etc.
    real_newlines = text.count("\n")
    return literal_newlines > real_newlines


_BACKSLASH_PLACEHOLDER = "\x00BS\x00"  # a byte sequence that never occurs in the corpus


def unescape(text: str) -> str:
    r"""Turn JSON-style escapes back into characters: \\n \\t \\" \\\\ \\uXXXX.

    Order matters. A double backslash means one real backslash, and must not be
    confused with the backslash that starts "\\n". So we park real backslashes in a
    placeholder first, unescape everything else, then put the backslashes back.

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
        return text  # nothing to do
    text = text.replace("\\\\", _BACKSLASH_PLACEHOLDER)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", _unicode_escape_to_char, text)
    text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")
    text = text.replace('\\"', '"')
    text = text.replace(_BACKSLASH_PLACEHOLDER, "\\")
    return text


def _unicode_escape_to_char(match: re.Match) -> str:
    r"""'\\u00e9' -> 'é'"""
    code_point = int(match.group(1), 16)
    return chr(code_point)


# ---------------------------------------------------------------------------
# Rule 2: structure fixes, so the Markdown parser sees what a human sees
# ---------------------------------------------------------------------------

WIKI_HEADING = re.compile(r"^h([1-6])\. (.+)$")        # "h2. Scope"
WIKI_TABLE_ROW = re.compile(r"^\|\|.*\|\|\s*$")          # "||Name||Owner||"
TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|\s*$")       # "|---|---:|"
SETEXT_UNDERLINE = re.compile(r"^(-{3,}|=+)\s*$")        # "-----" or "====="
LIST_ITEM_START = re.compile(r"^\s*(\d+[.)]|[a-z][.)]|[-*+]) ")  # "1) ", "a. ", "- "


def fix_structure(lines: list[str]) -> list[str]:
    """Walk the file line by line and rewrite the few shapes that confuse CommonMark.

    Input -> output (one example of each rewrite, in order):
        >>> fix_structure(["h2. Scope"])
        ['## Scope']
        >>> fix_structure(["||Name||Owner||", "| api | Ana |"])
        ['| Name | Owner |', '|---|---|', '| api | Ana |']
        >>> fix_structure(["1) Access", "---------", "Body"])
        ['## 1) Access', 'Body']
        >>> fix_structure(["| A | B |", "| 1 | 2 |"])
        ['| A | B |', '|---|---|', '| 1 | 2 |']
        >>> fix_structure(["plain text", "| A | B |", "|---|---|", "| 1 | 2 |"])   # already fine: unchanged
        ['plain text', '| A | B |', '|---|---|', '| 1 | 2 |']

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
            fixed.append(header_row)
            fixed.append(separator_row)
            i += 1

        elif _is_numbered_setext_heading(line, next_line):
            fixed.append(_setext_to_atx_heading(line, next_line))
            i += 2  # the underline is consumed too

        elif _is_table_header_without_separator(line, previous_line, next_line):
            fixed.append(line)
            fixed.append(_separator_row_for(line))
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
    header_row = "| " + " | ".join(cells) + " |"
    separator_row = "|" + "---|" * len(cells)
    return header_row, separator_row


def _is_numbered_setext_heading(line: str, next_line: str) -> bool:
    """A heading written as a list-looking line with an underline, e.g.
        1) Access & Permissions
        ----------------------
    CommonMark reads the first line as a list item and the underline as a rule, so the
    heading is lost. We rewrite it to '## 1) Access & Permissions' instead.

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
    """First row of a pipe table whose second row is data, not '|---|'.
    Without the separator, Markdown does not see a table at all.

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
    r"""Apply the structure fixes, then tidy whitespace:
    no trailing spaces, at most one blank line in a row, exactly one final newline.

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
        return ""  # an empty or whitespace-only file stays empty
    
    lines_without_trailing_spaces = [line.rstrip() for line in text.splitlines()]
    lines = fix_structure(lines_without_trailing_spaces)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def clean_one(raw: str) -> tuple[str, bool]:
    r"""Raw text -> (clean text, whether the file was unescaped).

    Input -> output:
        >>> clean_one("Title\n\nSummary:\\n\\n- one\\n- two\\n- three\\n- four\\n")
        ('Title\n\nSummary:\n\n- one\n- two\n- three\n- four\n', True)
        >>> clean_one("Title\n\nBody.\n")
        ('Title\n\nBody.\n', False)

    Edge cases:
        >>> clean_one("")
        ('', False)
    """
    escaped = is_escaped(raw)
    unescaped = unescape(raw) if escaped else raw
    return normalize(unescaped), escaped


def run(raw_dir: Path = RAW_DIR, clean_dir: Path = CLEAN_DIR):
    """Clean every raw file, write it next to a manifest, return (manifest, summary counts)."""
    clean_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    counts = {"escaped": 0, "unchanged": 0, "whitespace_only": 0, "structure_fixed": 0}

    for source in sorted(raw_dir.glob("*.txt")):
        raw = source.read_text(encoding="utf-8")
        clean, was_escaped = clean_one(raw)
        (clean_dir / source.name).write_text(clean, encoding="utf-8")

        if was_escaped:
            counts["escaped"] += 1
        elif clean == raw:
            counts["unchanged"] += 1
        else:
            counts["whitespace_only"] += 1
        if _structure_was_fixed(raw, was_escaped):
            counts["structure_fixed"] += 1

        manifest.append({
            "file": source.name,
            "raw_sha256": _sha256(raw),
            "clean_sha256": _sha256(clean),
            "was_escaped": was_escaped,
            "raw_lines": raw.count("\n") + 1,
            "clean_lines": clean.count("\n"),
            "raw_bytes": len(raw.encode()),
            "clean_bytes": len(clean.encode()),
        })

    (clean_dir / "_manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest, counts


def _structure_was_fixed(raw: str, was_escaped: bool) -> bool:
    text = unescape(raw) if was_escaped else raw
    lines = [line.rstrip() for line in text.splitlines()]
    return fix_structure(lines) != lines


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == "__main__":
    manifest, counts = run()
    print(f"{len(manifest)} files -> {CLEAN_DIR.relative_to(ROOT)}")
    print(json.dumps(counts, indent=1))

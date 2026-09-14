r"""Step 2 of the pipeline: work out how a clean file expresses its structure.

Two jobs live here.

1. bucket(text)       Which of four markup styles does the file use? This decides how
                      the chunker finds section boundaries.
2. label_flags(lines) The plain-label heading rule. For files with no heading markup,
                      decide line by line whether a line is a bare section label such
                      as "Overview" or "Rollout & Risk Controls".

Run:  uv run python -m pipeline.structure <file>
      debug one file: prints its bucket, then every line with HEADING / blank and the
      reason the rule decided that way.
      uv run python -m pipeline.structure
      buckets the clean corpus and reports how well the label rule recovers headings
      in files that carry real "#" markup (the markers are stripped first).

Why the label rule exists
-------------------------
More than half the corpus has no heading markup at all. The authors wrote

    Goals
    <blank>
    - Provide a repeatable acceptance checklist.

and a Markdown parser sees "Goals" as a one-word paragraph. Without this rule those
files would have no sections, and every chunk would lose its context line.

How the rule decides (in order)
-------------------------------
Line 1 is always the title.  Otherwise a line is a label when ALL of these hold:
  - it is label-shaped: short, not a block marker, no closing punctuation, not a
    sentence, not a "key: long value" line, contains real words  (see _is_label_shaped)
  - it is not indented and not inside a fenced code block
  - it is not a list item, EXCEPT a numbered line with a blank line above and below,
    which is a numbered heading ("3) Escalation heuristics"), not a list
  - the line above is blank, or is itself a label (stacked headings)

Validation: 0.92 recall against 25k real "#" headings with markers stripped (excluding
numbered headings, which the chunker keeps with their body anyway); ~90% precision on a
hand-checked sample. See docs/decisions/0001-confluence-parser.md.

Conventions: every deciding function shows "Input -> output" and "Edge cases" doctests,
run by tests/test_pipeline.py; trivial cases return early.
"""

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data/confluence/clean"


# ---------------------------------------------------------------------------
# Job 1: buckets
# ---------------------------------------------------------------------------

HASH_HEADING = re.compile(r"^#{1,6} ", re.M)                      # "## Scope"
SETEXT_HEADING = re.compile(r"^[^\n]{1,80}\n(=+|-{3,})\s*$", re.M)  # "Scope" over "-----"
LIST_TABLE_OR_FENCE = re.compile(r"^\s*([-*+]|\d+[.)]) |^\||^```", re.M)


def bucket(text: str) -> str:
    r"""Classify a file by the strongest structure signal it carries.

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
        >>> bucket("Intro\n-----\n\n# Real\n\n- item")     # "#" wins when both are present
        'A_hash'
    """
    if HASH_HEADING.search(text):
        return "A_hash"
    if SETEXT_HEADING.search(text):
        return "B_setext"
    if LIST_TABLE_OR_FENCE.search(text):
        return "C_plain_labels"
    return "D_prose"


# ---------------------------------------------------------------------------
# Job 2: the plain-label heading rule
# ---------------------------------------------------------------------------

MAX_LABEL_CHARS = 80
MAX_LABEL_WORDS = 12
BLOCK_MARKER = re.compile(r"^(\||>|```|#|---|\*\*\*|___|[{}\[\]])")  # table, quote, fence, heading, rule, json
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)]|[a-z][.)]) ")            # "- ", "1) ", "a. "
SENTENCE_STARTER = re.compile(r"^(We|This|The|It|If|You|Use|All) ")
KEY_COLON_VALUE = re.compile(r"^[^:]{1,40}: (.+)$")                    # "Owner: Identity team ..."
LABEL_LIKE_KEY = re.compile(                                            # "Stage 4:", "Q:", "Appendix B:"
    r"^(?:[A-Za-z]+ ?\d+[A-Za-z]?|[A-Za-z]+ [A-Z]|Q|Step|Phase|Stage|Case|Pattern|Example|Issue"
    r"|Scenario|Week|Day|Option|Playbook|Mitigation|Appendix|Part|Section|Tier|Level|Note):", re.I)
NUMBERED_LINE = re.compile(r"^(\d+[.)]|\d+(\.\d+)+) ")                # "3) ", "2. ", "10.1 "
HAS_A_WORD = re.compile(r"[A-Za-z]{2}")


def label_flags(lines: list[str]) -> list[bool]:
    """For each line, True if it is a section label. Same length as `lines`.

    Input -> output:
        >>> label_flags(["Title", "", "Overview", "", "Body text.", "", "Goals:", "- a"])
        [True, False, True, False, False, False, True, False]
        >>> label_flags(["Title", "", "Parent", "Child label", "", "Body."])   # stacked labels
        [True, False, True, True, False, False]

    Edge cases:
        >>> label_flags([])
        []
        >>> label_flags(["Title", "", "```", "", "def f():", "```", "", "After"])   # nothing inside a fence
        [True, False, False, False, False, False, False, True]
        >>> label_flags(["Title", "", "Body text.", "Not a label"])   # needs a blank line above
        [True, False, False, False]
    """
    if not lines:
        return []
    flags = [False] * len(lines)
    flags[0] = _is_title_line(lines[0])

    inside_fence = False
    for i in range(1, len(lines)):
        line = lines[i]
        if _is_fence_marker(line):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        if not _is_label_shaped(line.strip()) or _is_indented(line):
            continue
        line_above_is_blank = not lines[i - 1].strip()
        line_above_is_label = flags[i - 1]
        if LIST_ITEM.match(line) or NUMBERED_LINE.match(line):
            flags[i] = _is_numbered_heading(lines, i)
            continue
        flags[i] = line_above_is_blank or line_above_is_label
    return flags


def _is_numbered_heading(lines: list[str], i: int) -> bool:
    """A numbered line standing alone, blank above and below, is a heading not a list item.
    A tight list ("1) a" / "2) b") or an item with sub-bullets under it stays a list.

        >>> _is_numbered_heading(["T", "", "3) Escalation", "", "Body."], 2)
        True
        >>> _is_numbered_heading(["T", "", "1) first", "2) second"], 2)
        False
        >>> _is_numbered_heading(["T", "", "- bullet", "", "Body."], 2)     # only digits count
        False
    """
    if not NUMBERED_LINE.match(lines[i]):
        return False
    above_blank = not lines[i - 1].strip()
    below_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
    return above_blank and below_blank


def _is_title_line(line: str) -> bool:
    """Line 1 is the document title unless it is empty or opens a code fence."""
    return bool(line.strip()) and not line.startswith("```")


def _is_fence_marker(line: str) -> bool:
    return line.lstrip().startswith("```")


def _is_indented(line: str) -> bool:
    return line[:1].isspace()


def _is_label_shaped(s: str) -> bool:
    """Does this stripped line look like a section label, ignoring its neighbours?

    Input -> output:
        >>> _is_label_shaped("Rollout & Risk Controls")
        True
        >>> _is_label_shaped("Phase 1: Data-source plumbing (Week 1-3)")
        True
        >>> _is_label_shaped("Testing, canaries and chaos simulation:")
        True

    Rejected, one example per reason:
        >>> _is_label_shaped("x" * 81)                                     # too long
        False
        >>> _is_label_shaped("| a | b |")                                  # block marker
        False
        >>> _is_label_shaped("Ends with a period.")                        # closing punctuation
        False
        >>> _is_label_shaped("The quick brown fox jumps over the lazy dog, twice, today")   # sentence-like
        False
        >>> _is_label_shaped("We should not treat this as a heading")      # sentence starter
        False
        >>> _is_label_shaped("Owner: Identity and Access team, second approver required")  # key: long value
        False
        >>> _is_label_shaped("--kvcache-async")                            # no real word / flag-like
        False

    Edge cases:
        >>> _is_label_shaped("")
        False
    """
    if not s:
        return False
    if len(s) > MAX_LABEL_CHARS or len(s.split()) > MAX_LABEL_WORDS:
        return False
    if BLOCK_MARKER.match(s):
        return False
    if s[-1] in ".;,":
        return False
    if _looks_like_a_sentence(s):
        return False
    if _is_key_with_long_value(s):
        return False
    if not HAS_A_WORD.search(s) or s.startswith(("-", "/")):
        return False
    return True


def _looks_like_a_sentence(s: str) -> bool:
    """Long clause with a comma, or starts like prose.

        >>> _looks_like_a_sentence("The service restarts on failure")
        True
        >>> _looks_like_a_sentence("Testing, canaries and chaos simulation:")   # short: still a label
        False
    """
    has_comma_and_many_words = "," in s and len(s.split()) > 8
    return has_comma_and_many_words or SENTENCE_STARTER.match(s) is not None


def _is_key_with_long_value(s: str) -> bool:
    """'Owner: Identity and Access team (eng-infra) is here' is a field, not a heading.
    A short value or a trailing colon is still allowed ('Appendix: Mappings', 'Goals:'),
    and so is a label-like key: 'Stage 4: ...', 'Q: ...', 'Appendix B: ...'.

        >>> _is_key_with_long_value("Owner: Identity and Access team second approver required")
        True
        >>> _is_key_with_long_value("Appendix: Example Mappings")
        False
        >>> _is_key_with_long_value("Goals:")
        False
        >>> _is_key_with_long_value("Stage 4: Expand to Dedicated and Private deployments today")
        False
        >>> _is_key_with_long_value("Q: Can we extend a lease mid-window for a customer?")
        False
    """
    if s.endswith(":") or LABEL_LIKE_KEY.match(s):
        return False
    match = KEY_COLON_VALUE.match(s)
    if match is None:
        return False
    value_words = match.group(1).split()
    return len(value_words) >= 6


def labels(text: str) -> list[tuple[int, str]]:
    r"""Convenience: (1-based line number, label text) for every label in a document.

        >>> labels("Title\n\nOverview\n\nBody.")
        [(1, 'Title'), (3, 'Overview')]
    """
    lines = text.splitlines()
    flags = label_flags(lines)
    return [(i + 1, lines[i].strip()) for i in range(len(lines)) if flags[i]]


# ---------------------------------------------------------------------------
# Debugging: explain the decision for every line of one file
# ---------------------------------------------------------------------------

def explain(text: str) -> list[dict]:
    r"""One row per line: {"line", "decision", "reason", "text"}. decision is "HEADING" or "".

        >>> for row in explain("Title\n\nGoals\n- item"): print(row["line"], row["decision"] or "-", row["reason"])
        1 HEADING line 1 is the title
        2 - blank
        3 HEADING label-shaped, blank line above
        4 - list item
    """
    lines = text.splitlines()
    if not lines:
        return []
    flags = label_flags(lines)
    rows = []
    inside_fence = False
    for i, line in enumerate(lines):
        if _is_fence_marker(line):
            inside_fence = not inside_fence
            reason = "code fence marker"
        elif inside_fence:
            reason = "inside code fence"
        elif i == 0:
            reason = "line 1 is the title" if flags[0] else "empty title line"
        else:
            reason = _reason_for(lines, i, flags)
        rows.append({"line": i + 1, "decision": "HEADING" if flags[i] else "", "reason": reason, "text": line})
    return rows


def _reason_for(lines: list[str], i: int, flags: list[bool]) -> str:
    """Which check decided line i (i >= 1, not in a fence)."""
    line = lines[i]
    s = line.strip()
    if not s:
        return "blank"
    if LIST_ITEM.match(line) or NUMBERED_LINE.match(line):
        if flags[i]:
            return "numbered heading: blank line above and below"
        return "list item"
    if _is_indented(line):
        return "indented"
    if len(s) > MAX_LABEL_CHARS or len(s.split()) > MAX_LABEL_WORDS:
        return f"too long (>{MAX_LABEL_CHARS} chars or >{MAX_LABEL_WORDS} words)"
    if BLOCK_MARKER.match(s):
        return "starts with a block marker (table, quote, #, ---, {)"
    if s[-1] in ".;,":
        return "ends with . ; or ,"
    if _looks_like_a_sentence(s):
        return "looks like a sentence"
    if _is_key_with_long_value(s):
        return "key: long value (a field, not a heading)"
    if not HAS_A_WORD.search(s) or s.startswith(("-", "/")):
        return "no real word, or starts with - or /"
    if flags[i]:
        return "label-shaped, blank line above" if not lines[i - 1].strip() else "label-shaped, stacked under the heading above"
    return "label-shaped, but the line above is text (no blank line)"


# ---------------------------------------------------------------------------
# Self-check: how well does the rule recover headings we can verify?
# ---------------------------------------------------------------------------

ATX_HEADING_LINE = re.compile(r"^#{1,6} (.+)$")


def recall_against_hash_headings(texts: list[str]) -> dict:
    r"""Strip the "#" markers from files that have them, run the label rule, and count how
    many of the real headings it finds. Precision is NOT meaningful here: these files also
    contain bare labels the markers never marked, and the rule is right to find those.

        >>> recall_against_hash_headings(["# Title\n\n## Scope\n\nBody.\n\n## Goals\n\n- a"])
        {'true_headings': 3, 'found': 3, 'recall': 1.0}
        >>> recall_against_hash_headings(["no headings"])
        {'true_headings': 0, 'found': 0, 'recall': None}
    """
    true_headings = found = 0
    for text in texts:
        stripped_lines, heading_indexes = _strip_heading_markers(text.splitlines())
        flags = label_flags(stripped_lines)
        true_headings += len(heading_indexes)
        found += sum(1 for i in heading_indexes if flags[i])
    recall = found / true_headings if true_headings else None
    return {"true_headings": true_headings, "found": found, "recall": recall}


def _strip_heading_markers(lines: list[str]) -> tuple[list[str], set[int]]:
    """'## Scope' -> 'Scope', remembering which line indexes were headings."""
    stripped, heading_indexes = [], set()
    for i, line in enumerate(lines):
        match = ATX_HEADING_LINE.match(line)
        if match:
            stripped.append(match.group(1).strip())
            heading_indexes.add(i)
        else:
            stripped.append(line)
    return stripped, heading_indexes


def bucket_corpus(clean_dir: Path = CLEAN_DIR) -> dict[str, list[str]]:
    """{bucket name: [file names]} for every clean file; also saved as _buckets.json."""
    by_bucket = collections.defaultdict(list)
    for path in sorted(clean_dir.glob("*.txt")):
        by_bucket[bucket(path.read_text())].append(path.name)
    (clean_dir / "_buckets.json").write_text(json.dumps(by_bucket, indent=1))
    return dict(by_bucket)


def _print_explanation(path: Path) -> None:
    text = path.read_text()
    print(f"{path.name}\nbucket: {bucket(text)}\n")
    for row in explain(text):
        print(f"{row['line']:4d} {row['decision']:8s} {row['reason']:52s} | {row['text'][:60]}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        _print_explanation(Path(sys.argv[1]))
        sys.exit(0)
    by_bucket = bucket_corpus()
    total = sum(len(v) for v in by_bucket.values())
    print(f"total {total}")
    for name in sorted(by_bucket):
        print(f"  {name:16s} {len(by_bucket[name]):5d}  {100 * len(by_bucket[name]) / total:5.1f}%")
    # The recall check needs the text of every file that has real "#" headings.
    files_with_hash_headings = by_bucket.get("A_hash", [])
    texts = []
    for file_name in files_with_hash_headings:
        texts.append((CLEAN_DIR / file_name).read_text())
    report = recall_against_hash_headings(texts)
    print(f"\nLabel rule vs real '#' headings in bucket A: {report}")

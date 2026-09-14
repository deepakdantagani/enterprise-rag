"""PARSE-4: the plain-label heading rule.

53% of clean files have headings with no markup: a short bare line such as
"Overview:" or "High-level design" with a blank line above it. This module flags
those lines. Two halves:

    shape       does this one line look like a label?          (4a, 4b)
    neighbours  is it in a place where a label can be?         (4c, 4d)

Pure module: it is handed lines and returns booleans.
"""
import re

MAX_LABEL_CHARS = 80
MAX_LABEL_WORDS = 12
BLOCK_MARKER = re.compile(r"^(\||>|```|#|---|\*\*\*|___|[{}\[\]])")  # table, quote, fence, heading, rule, json
HAS_A_WORD = re.compile(r"[A-Za-z]{2}")
NUMBERED_LINE = re.compile(r"^(\d+[.)]|\d+(\.\d+)+) ")                # "3) ", "2. ", "10.1 "
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)]|[a-z][.)]) ")            # "- ", "1) ", "a. "
SENTENCE_STARTER = re.compile(r"^(We|This|The|It|If|You|Use|All) ")
KEY_COLON_VALUE = re.compile(r"^[^:]{1,40}: (.+)$")                    # "Owner: Identity team ..."
LABEL_LIKE_KEY = re.compile(                                            # "Stage 4:", "Q:", "Appendix B:"
    r"^(?:[A-Za-z]+ ?\d+[A-Za-z]?|[A-Za-z]+ [A-Z]|Q|Step|Phase|Stage|Case|Pattern|Example|Issue"
    r"|Scenario|Week|Day|Option|Playbook|Mitigation|Appendix|Part|Section|Tier|Level|Note):", re.I)


def looks_like_a_sentence(line: str) -> bool:
    """Prose, not a label: starts like a sentence, or is a long clause with a comma.

    Input -> output:
        >>> looks_like_a_sentence("The service restarts on failure")
        True
        >>> looks_like_a_sentence("Manual triage is slow, remediation must be conservative, safe, and audited")
        True
        >>> looks_like_a_sentence("Testing, canaries and chaos simulation:")   # short: still a label
        False

    Edge cases:
        >>> looks_like_a_sentence("")
        False
    """
    has_comma_and_many_words = "," in line and len(line.split()) > 8
    return has_comma_and_many_words or SENTENCE_STARTER.match(line) is not None


def is_key_with_long_value(line: str) -> bool:
    """A field like "Owner: Identity and Access team ..." is data, not a heading.

    "Long" means the value has 6 or more words. Allowed as labels: a trailing colon
    ("Goals:"), a short value ("Appendix: Mappings"), or a label-like key
    ("Stage 4: ...", "Q: ...", "Appendix B: ...").

    Input -> output:
        >>> is_key_with_long_value("Owner: Identity and Access team second approver required")
        True
        >>> is_key_with_long_value("Goals:")
        False
        >>> is_key_with_long_value("Appendix: Example Mappings")
        False
        >>> is_key_with_long_value("Stage 4: Expand to Dedicated deployments today")
        False
        >>> is_key_with_long_value("Q: Can we extend a lease mid-window?")
        False

    Edge cases:
        >>> is_key_with_long_value("High-level design")     # no colon
        False
        >>> is_key_with_long_value("Owner: one two three four five")        # 5 words: short
        False
        >>> is_key_with_long_value("Owner: one two three four five six")    # 6 words: long
        True
    """
    if line.endswith(":") or LABEL_LIKE_KEY.match(line):
        return False
    match = KEY_COLON_VALUE.match(line)
    if match is None:
        return False
    return len(match.group(1).split()) >= 6


def is_label_shaped(line: str) -> bool:
    """Does this one stripped line have the shape of a section label?

    No accept rule: a chain of reject checks, in this order; True if none fires.
    Shape is necessary, not sufficient: label_flags (4d) also checks the neighbours.

    Input -> output:
        >>> is_label_shaped("Rollout & Risk Controls")
        True
        >>> is_label_shaped("Phase 1: Data-source plumbing (Week 1-3)")   # label-like key
        True
        >>> is_label_shaped("Testing, canaries and chaos simulation:")    # trailing colon, short
        True

    Rejected, one example per reason:
        >>> is_label_shaped("x" * 81)                                  # too long
        False
        >>> is_label_shaped("| a | b |")                               # block marker
        False
        >>> is_label_shaped("Ends with a period.")                     # closing punctuation
        False
        >>> is_label_shaped("We should not treat this as a heading")   # sentence (4a)
        False
        >>> is_label_shaped("Owner: Identity and Access team second approver required")  # field (4a)
        False
        >>> is_label_shaped("--kvcache-async")                         # no real word, flag-like
        False

    Edge cases:
        >>> is_label_shaped("")
        False
    """
    if not line:
        return False
    if len(line) > MAX_LABEL_CHARS or len(line.split()) > MAX_LABEL_WORDS:
        return False
    if BLOCK_MARKER.match(line):
        return False
    if line[-1] in ".;,":
        return False
    if looks_like_a_sentence(line):
        return False
    if is_key_with_long_value(line):
        return False
    if not HAS_A_WORD.search(line) or line.startswith(("-", "/")):
        return False
    return True


def is_numbered_heading(lines: list[str], i: int) -> bool:
    """A numbered line standing alone, blank above and below, is a heading, not a list item.

    A tight list ("1) a" / "2) b") or an item with sub-bullets under it stays a list.
    The last line of the file counts as having a blank line below.

    Input -> output:
        >>> is_numbered_heading(["T", "", "3) Escalation", "", "Body."], 2)
        True
        >>> is_numbered_heading(["T", "", "1) first", "2) second"], 2)
        False
        >>> is_numbered_heading(["T", "", "10.1 Sub-section", "", "Body."], 2)
        True

    Edge cases:
        >>> is_numbered_heading(["T", "", "- bullet", "", "Body."], 2)   # only digits count
        False
        >>> is_numbered_heading(["T", "", "3) Escalation"], 2)          # last line
        True
    """
    if not NUMBERED_LINE.match(lines[i]):
        return False
    above_blank = not lines[i - 1].strip()
    below_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
    return above_blank and below_blank


def label_flags(lines: list[str]) -> list[bool]:
    """For each line, True if it is a section heading. Same length as `lines`.

    Line 1 is the title. Every other line must be label-shaped (4b), not indented,
    not inside a code fence, and either have a blank line above or sit directly under
    another label (stacked). List items and numbered lines go through 4c instead.

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
    flags[0] = is_title_line(lines[0])

    inside_fence = False
    for i in range(1, len(lines)):
        line = lines[i]
        if is_fence_marker(line):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        if not is_label_shaped(line.strip()) or is_indented(line):
            continue
        if LIST_ITEM.match(line) or NUMBERED_LINE.match(line):
            flags[i] = is_numbered_heading(lines, i)
            continue
        line_above_is_blank = not lines[i - 1].strip()
        line_above_is_label = flags[i - 1]
        flags[i] = line_above_is_blank or line_above_is_label
    return flags


def is_title_line(line: str) -> bool:
    """Line 1 is the document title unless it is empty or opens a code fence.

        >>> is_title_line("Scheduler Health Oracle")
        True
        >>> is_title_line(""), is_title_line("```")
        (False, False)
    """
    return bool(line.strip()) and not line.startswith("```")


def is_fence_marker(line: str) -> bool:
    """Opens or closes a code block.

        >>> is_fence_marker("```python"), is_fence_marker("  ```"), is_fence_marker("code")
        (True, True, False)
    """
    return line.lstrip().startswith("```")


def is_indented(line: str) -> bool:
    """Starts with whitespace: continuation or nested content, never a heading.

        >>> is_indented("  Indented"), is_indented("Flush")
        (True, False)
    """
    return line[:1].isspace()

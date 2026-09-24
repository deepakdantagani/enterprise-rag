r"""SLACK-2: repair whitespace in a Slack thread without touching list or code indentation.

Runs on the output of SLACK-1. Each rule is one function that returns the new text and how
many changes it made; RULES lists them in the order they run. The order is part of the
contract: carriage returns become line feeds first, so every later rule sees plain lines.

The sharp edge is the indented speaker line, indented by exactly one space or one tab:

    ' tom_ae: FYI customer claims integrations built during POC...'

The same shape is also an HTTP header or YAML (` Host: api.redwood.example`,
` enabled: true`), so the indent goes only when the line starts a message (it follows a
blank line) or its name speaks at least twice in the thread. Deeper indents are YAML or
code (`  max_retries: 5`), and anything between ``` fences is code: both keep their
indentation. Trailing whitespace and blank-line runs are tidied everywhere, code included.

Pure: text in, WhitespaceResult out. No files, no events; the caller (SLACK-4) does both.

    >>> normalize_whitespace("sales\n\njen: sync \n\n tom_ae: FYI")
    WhitespaceResult(text='sales\n\njen: sync\n\ntom_ae: FYI\n', rules_fired={'indented_speaker': 1, 'trailing_whitespace': 1, 'final_newline': 1})
"""
import re
from collections import Counter
from dataclasses import dataclass

CARRIAGE_RETURN = re.compile(r"\r\n?")
NON_BREAKING_SPACE = "\u00a0"
SPEAKER = r"([A-Za-z][\w.\-]*)(?: \([^)\n]{1,40}\))?: "  # `tom_ae: ` or `dylan (finance): `
SPEAKER_LINE = re.compile(rf"[ \t]?{SPEAKER}")
INDENTED_SPEAKER_LINE = re.compile(rf"[ \t]{SPEAKER}")
SPEAKS_OFTEN_ENOUGH = 2  # an indented name that speaks this often in the thread is a speaker
CODE_FENCE = "```"
TRAILING_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)
BLANK_LINE_RUN = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class WhitespaceResult:
    text: str
    rules_fired: dict[str, int]  # rule name -> changes it made; empty if untouched


def normalize_whitespace(text: str) -> WhitespaceResult:
    """Apply every rule in RULES, in order, and count what each one changed."""
    rules_fired = {}
    for rule_name, apply_rule in RULES:
        text, changes = apply_rule(text)
        if changes:
            rules_fired[rule_name] = changes
    return WhitespaceResult(text, rules_fired)


def unify_line_breaks(text: str) -> tuple[str, int]:
    r"""\r\n and a lone \r both become \n."""
    return CARRIAGE_RETURN.subn("\n", text)


def replace_non_breaking_spaces(text: str) -> tuple[str, int]:
    return text.replace(NON_BREAKING_SPACE, " "), text.count(NON_BREAKING_SPACE)


def straighten_speaker_lines(text: str) -> tuple[str, int]:
    r"""Drop the one-character indent of a speaker line, but never inside a code fence.

    >>> straighten_speaker_lines("eng\n\n tom: hi\n Host: api.x\n```\n tom: code\n```")
    ('eng\n\ntom: hi\n Host: api.x\n```\n tom: code\n```', 1)
    """
    lines = text.split("\n")
    inside_code = code_fence_flags(lines)
    times_spoken = speaker_counts(lines, inside_code)
    changes = 0
    for index, line in enumerate(lines):
        indented = None if inside_code[index] else INDENTED_SPEAKER_LINE.match(line)
        if not indented:
            continue
        starts_message = index == 0 or not lines[index - 1].strip()
        if starts_message or times_spoken[indented.group(1)] >= SPEAKS_OFTEN_ENOUGH:
            lines[index] = line[1:]
            changes += 1
    return "\n".join(lines), changes


def speaker_counts(lines: list[str], inside_code: list[bool]) -> Counter:
    """How many lines outside code each name opens, indented by at most one character."""
    return Counter(
        match.group(1)
        for line, in_code in zip(lines, inside_code)
        if not in_code and (match := SPEAKER_LINE.match(line))
    )


def code_fence_flags(lines: list[str]) -> list[bool]:
    r"""For each line, True if it starts inside a code block.

    Any line with an odd number of ``` opens or closes a block, wherever the fence sits
    (`kai: logs:```` opens one). An even number (```/poll "WFH"```) is inline code.

    >>> code_fence_flags(["a", "kai: logs:```", "b", "```", "c ```x``` d"])
    [False, False, True, True, False]
    """
    flags, inside_code = [], False
    for line in lines:
        flags.append(inside_code)
        if line.count(CODE_FENCE) % 2 == 1:
            inside_code = not inside_code
    return flags


def strip_trailing_whitespace(text: str) -> tuple[str, int]:
    return TRAILING_WHITESPACE.subn("", text)


def collapse_blank_line_runs(text: str) -> tuple[str, int]:
    """Two or more blank lines in a row become one."""
    return BLANK_LINE_RUN.subn("\n\n", text)


def end_with_one_newline(text: str) -> tuple[str, int]:
    """Exactly one final newline; an empty thread stays empty."""
    ended = text.rstrip("\n") + "\n" if text.strip("\n") else ""
    return ended, int(ended != text)


RULES = (  # (rule name, function), in the order they run
    ("carriage_return", unify_line_breaks),
    ("non_breaking_space", replace_non_breaking_spaces),
    ("indented_speaker", straighten_speaker_lines),
    ("trailing_whitespace", strip_trailing_whitespace),
    ("blank_line_run", collapse_blank_line_runs),
    ("final_newline", end_with_one_newline),
)

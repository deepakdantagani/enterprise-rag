r"""SLACK-2: repair whitespace in a Slack thread without touching list or code indentation.

Runs on the output of SLACK-1. Each rule is one function that returns the new text and how
many changes it made; RULES lists them in the order they run. The order is part of the
contract: carriage returns become line feeds first, so every later rule sees plain lines.

The sharp edge is the indented speaker line. 1,544 threads have one, and it is always
indented by exactly one space or one tab:

    ' tom_ae: FYI customer claims integrations built during POC...'

Deeper indents are YAML or code (`  max_retries: 5`), and anything between ``` fences is
code, so both keep their indentation.

Pure: text in, WhitespaceResult out. No files, no events; the caller (SLACK-4) does both.

    >>> normalize_whitespace("sales\n\njen: sync \n tom_ae: FYI")
    WhitespaceResult(text='sales\n\njen: sync\ntom_ae: FYI\n', rules_fired={'indented_speaker': 1, 'trailing_whitespace': 1, 'final_newline': 1})
"""
import re
from dataclasses import dataclass

CARRIAGE_RETURN = re.compile(r"\r\n?")
NON_BREAKING_SPACE = " "
# One space or one tab, then a speaker prefix: `tom_ae: ` or `dylan (finance): `.
SPEAKER_INDENT = re.compile(r"[ \t](?=[A-Za-z][\w.\-]*(?: \([^)\n]{1,40}\))?: )")
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

    >>> straighten_speaker_lines(" tom: hi\n```\n tom: code\n```")
    ('tom: hi\n```\n tom: code\n```', 1)
    """
    lines = text.split("\n")
    changes = 0
    for index, inside_code in enumerate(code_fence_flags(lines)):
        if not inside_code and SPEAKER_INDENT.match(lines[index]):
            lines[index] = lines[index][1:]
            changes += 1
    return "\n".join(lines), changes


def code_fence_flags(lines: list[str]) -> list[bool]:
    r"""For each line, True if it is a fence line or sits between two fences.

    A line holding an even number of ``` (inline code, `/poll` in ```...```) opens nothing.

    >>> code_fence_flags(["a", "```", "b", "```", "c ```x``` d", "e"])
    [False, True, True, True, False, False]
    """
    flags, inside_code = [], False
    for line in lines:
        opens_or_closes = line.lstrip().startswith(CODE_FENCE) and line.count(CODE_FENCE) % 2 == 1
        flags.append(inside_code or opens_or_closes)
        if opens_or_closes:
            inside_code = not inside_code
    return flags


def strip_trailing_whitespace(text: str) -> tuple[str, int]:
    return TRAILING_WHITESPACE.subn("", text)


def collapse_blank_line_runs(text: str) -> tuple[str, int]:
    """Two or more blank lines in a row become one."""
    return BLANK_LINE_RUN.subn("\n\n", text)


def end_with_one_newline(text: str) -> tuple[str, int]:
    ended = text.rstrip("\n") + "\n"
    return ended, int(ended != text)


RULES = (  # (rule name, function), in the order they run
    ("carriage_return", unify_line_breaks),
    ("non_breaking_space", replace_non_breaking_spaces),
    ("indented_speaker", straighten_speaker_lines),
    ("trailing_whitespace", strip_trailing_whitespace),
    ("blank_line_run", collapse_blank_line_runs),
    ("final_newline", end_with_one_newline),
)

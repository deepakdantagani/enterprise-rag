"""SLACK-6: cut a clean Slack thread into its messages.

A message starts at a line that opens with a speaker, outside a code block. That one rule
covers both export layouts: a blank line between messages (149,429 threads) and one message
per line (108,460). A blank line is not a boundary: 12,569 threads have one inside code.

Speakers come in these shapes (SPEAKER_AT_LINE_START):

    tom_ae:           Aisha (CS):           Maya Chen:        Priya S.:
    maria gonzalez:   Maya - People Ops:    Connor O'Brien:   Incident Bot:

A line shaped like that is not always a speaker. `Due: 2026-04-02`, `Note: ...` and
`Content-Type: application/json` are labels inside a message: a name whose first word is in
NOT_SPEAKERS is one, unless it ends in `Bot` (`Status Bot:`). Team handles (`ops:`,
`support:`, `Customer Success:`) do speak, so they are not in the table. A name of two or
three words with a lowercase word after the first (`maria gonzalez`, but also
`browser console`) counts only if it opens two or more lines in the thread: people speak
again, labels rarely repeat.

Code-block detection is SLACK-2's `code_fence_flags`, reused; a fence left open at the end of
a thread (`sre-oncall: executing step A now.```) is treated as a typo and ignored, so it
cannot swallow the messages after it. No LlamaIndex parser splits chat by speaker: its
splitters cut by size or by markup.

Pure: the text of one clean thread in, Split(header, messages) out. Nothing is dropped:
`header + "".join(messages) == text`, byte for byte. The header is whatever comes before the
first message (the channel line and blank line, an export path, a summary); a message keeps
its own trailing line breaks.

    >>> split_messages("eng\\n\\nkai: paging\\nDue: today\\n\\nops: on it\\n")
    Split(header='eng\\n\\n', messages=['kai: paging\\nDue: today\\n\\n', 'ops: on it\\n'])
"""
import re
from collections import Counter
from typing import NamedTuple

from pipeline.slack.whitespace import CODE_FENCE, code_fence_flags

NAME_WORD = r"[A-Za-z][\w.'\-]*"
SPEAKER_AT_LINE_START = re.compile(
    rf"(?P<name>[A-Za-z][\w.\-]*(?: {NAME_WORD}){{0,2}})"  # tom_ae, Maya Chen, maria gonzalez, Priya S.
    r"(?: - (?P<team>[\w&][\w &\-]{0,24}))?"               # - People Ops
    r"(?: \((?P<role>[^)\n]{1,40})\))?: "                  # (CS)
)
BOT_SUFFIX = "bot"
REPEATS_NEEDED = 2  # a lowercase multi-word name must open this many lines to count
NOT_SPEAKERS = frozenset({  # first words of labels, measured opening a line inside a message
    "note", "notes", "response", "resp", "result", "results", "body", "also", "all", "today",
    "summary", "status", "error", "errors", "output", "example", "expected", "actual",
    "impact", "owner", "owners", "plan", "goal", "due", "action", "actions", "next", "context",
    "question", "answer", "q", "a", "decision", "why", "ask", "fix", "cause", "reason", "root",
    "update", "tldr", "eta", "link", "links", "logs", "log", "trace", "traceback", "repro",
    "run", "cmd", "command", "request", "reply", "subject", "to", "from", "cc", "re", "date",
    "time", "host", "content-type", "authorization", "headers", "env", "pr", "ticket", "issue",
    "steps", "step", "user", "assistant", "system", "prompt", "input", "warning", "warn",
    "info", "fatal", "panic", "exception", "data", "model", "commit", "metrics", "metric",
    "tag", "labels", "kind", "target", "service", "ref", "region", "total", "alert", "title",
    "timeline", "proposal", "account", "mitigation", "before", "after", "duration", "config",
    "option", "severity", "client", "id", "deadline", "version", "p95",
})


class Split(NamedTuple):
    header: str          # everything before the first message; may be empty
    messages: list[str]  # each from its speaker line up to the next one


def split_messages(text: str) -> Split:
    """Cut text at every line that opens a message."""
    lines = text.split("\n")
    line_starts = line_offsets(lines)
    cuts = [line_starts[index] for index in message_start_lines(lines)] + [len(text)]
    return Split(text[: cuts[0]], [text[start:end] for start, end in zip(cuts, cuts[1:])])


def message_start_lines(lines: list[str]) -> list[int]:
    """Indexes of the lines that open a message: a speaker, outside code, not a label."""
    inside_code = code_flags_ignoring_an_unclosed_fence(lines)
    speakers = {index: match["name"] for index, line in enumerate(lines)
                if not inside_code[index] and (match := SPEAKER_AT_LINE_START.match(line))}
    times_named = Counter(name.lower() for name in speakers.values())
    return [index for index, name in speakers.items() if is_speaker(name, times_named[name.lower()])]


def is_speaker(name: str, times_named: int) -> bool:
    """True for a person, bot or team; False for a label, or a one-off lowercase phrase.

    >>> is_speaker("Aisha", 1), is_speaker("Due", 1), is_speaker("Status Bot", 1)
    (True, False, True)
    >>> is_speaker("maria gonzalez", 2), is_speaker("browser console", 1)
    (True, False)
    """
    words = name.split()
    if words[-1].lower() == BOT_SUFFIX:
        return True
    if words[0].lower() in NOT_SPEAKERS:
        return False
    lowercase_after_first = any(word[0].islower() for word in words[1:])
    return not lowercase_after_first or times_named >= REPEATS_NEEDED


def code_flags_ignoring_an_unclosed_fence(lines: list[str]) -> list[bool]:
    """SLACK-2's code_fence_flags, but a fence that never closes does not open a block.

    >>> code_flags_ignoring_an_unclosed_fence(["a```", "b", "```", "c: done.```", "d: ok"])
    [False, True, True, False, False]
    """
    flags = code_fence_flags(lines)
    if not ends_inside_code(lines, flags):
        return flags
    last_fence = max(index for index, line in enumerate(lines) if line.count(CODE_FENCE) % 2 == 1)
    return flags[: last_fence + 1] + [False] * (len(lines) - last_fence - 1)


def ends_inside_code(lines: list[str], flags: list[bool]) -> bool:
    """True when the thread is still inside a code block after its last line."""
    last_line_opens_or_closes = lines[-1].count(CODE_FENCE) % 2 == 1
    return flags[-1] != last_line_opens_or_closes


def line_offsets(lines: list[str]) -> list[int]:
    """Where each line starts in the text they were split from."""
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1
    return offsets

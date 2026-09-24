"""SLACK-6: cut a clean Slack thread into its messages.

A message starts at a line that opens with a speaker, `Aisha (CS): ` or `deploy-bot: `,
outside a code block. That one rule covers both export layouts: a blank line between
messages (149,429 threads) and one message per line (108,460). A blank line is not a
boundary: 12,569 threads have one inside a code block.

A line shaped like a speaker is not always one. `Due: 2026-04-02`, `Note: ...` and
`Content-Type: application/json` are labels inside a message, so NOT_SPEAKERS lists the
words measured opening a line as a label. Team handles (`ops:`, `legal:`, `support:`) do
speak, so they are not in it.

Code-block detection is SLACK-2's `code_fence_flags`, reused as is; the speaker pattern is
SLACK-2's widened to full names.
No LlamaIndex parser splits chat by speaker: its splitters cut by size or by markup.

Pure: the text of one clean thread in, Split(header, messages) out. Nothing is dropped:
`header + "".join(messages) == text`, byte for byte. The header is whatever comes before the
first message (the channel line and blank line, an export path, a summary); a message keeps
its own trailing line breaks.

    >>> split_messages("eng\\n\\nkai: paging\\nDue: today\\n\\nops: on it\\n")
    Split(header='eng\\n\\n', messages=['kai: paging\\nDue: today\\n\\n', 'ops: on it\\n'])
"""
import re
from typing import NamedTuple

from pipeline.slack.whitespace import code_fence_flags

# SLACK-2's speaker (`tom_ae: `, `dylan (finance): `), widened to full names: 40,141 threads
# have `Maya Chen: `, `Priya S.: ` or `Connor O'Brien: `. SLACK-2 keeps its narrower pattern:
# it only straightens indents, and widening it would change the clean corpus.
SPEAKER_AT_LINE_START = re.compile(r"([A-Za-z][\w.\-]*(?: [A-Z][\w.'\-]*){0,2})(?: \([^)\n]{1,40}\))?: ")
NOT_SPEAKERS = frozenset({  # label words measured opening a line inside a message (lowercased)
    "note", "notes", "response", "result", "results", "body", "also", "all", "today",
    "summary", "status", "error", "errors", "output", "example", "expected", "actual",
    "impact", "owner", "owners", "plan", "goal", "due", "action", "actions", "next", "context",
    "question", "answer", "q", "a", "decision", "why", "ask", "fix", "cause", "root", "update",
    "tldr", "eta", "link", "links", "logs", "log", "trace", "traceback", "repro", "run", "cmd",
    "command", "request", "reply", "subject", "to", "from", "cc", "re", "date", "time", "host",
    "content-type", "authorization", "env", "pr", "ticket", "issue", "steps", "step",
    "user", "assistant", "system", "prompt", "input",
    "warning", "warn", "info", "fatal", "panic", "exception",
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
    return [
        index
        for index, (line, inside_code) in enumerate(zip(lines, code_fence_flags(lines)))
        if not inside_code and opens_message(line)
    ]


def opens_message(line: str) -> bool:
    """
    A name is a label when its first word is one: `Plan B: `, `Response A: `.

    >>> opens_message("Aisha (CS): Hey team"), opens_message("Maya Chen: ok"), opens_message("Due: 2026-04-02")
    (True, True, False)
    """
    speaker = SPEAKER_AT_LINE_START.match(line)
    return speaker is not None and speaker.group(1).split()[0].lower() not in NOT_SPEAKERS


def line_offsets(lines: list[str]) -> list[int]:
    """Where each line starts in the text they were split from."""
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1
    return offsets

r"""GMAIL-3: cut a clean Gmail thread into its title, a preamble and one block per message.

Entry point:  split_messages(text) -> SplitThread(title, preamble, blocks)

The only structure in this corpus is the message boundary: `From:` at the start of a line
(92 of 121,390 threads hold a Markdown heading, so there are no sections). A quoted
`> From:` or a mid-line `From:` is not at the start of a line, so it never cuts.

    Renewal notes
                                        title      line 1
    From: Ana <ana@x.com>               block 1    from a From: line to the next one
    ...
    From: Raj <raj@x.com>               block 2

Lines between the title and the first `From:` are the preamble. 609 threads have one: a
`Date:` line, a `--- Message 1 ---` marker or a one-paragraph summary. It is kept, so no
non-blank line is lost; moving a date into its block, or dropping markers, is GMAIL-3b.
The 189 threads with no `From:` give one block holding the whole body, so their id is still
reachable; that block does not start with `From:`, which is how a caller tells it apart.

    >>> split_messages("T\n\nnote\nFrom: a\n\nhi\n\nFrom: b\nyo\n")
    SplitThread(title='T', preamble='note', blocks=['From: a\n\nhi', 'From: b\nyo'])
    >>> split_messages("Re: x\n\nHi Nikhil,\n")
    SplitThread(title='Re: x', preamble='', blocks=['Hi Nikhil,'])
"""
from dataclasses import dataclass

MESSAGE_START = "From:"


@dataclass(frozen=True)
class SplitThread:
    title: str
    preamble: str
    blocks: list[str]


def split_messages(text: str) -> SplitThread:
    """Cut a clean thread at every line that starts with `From:`."""
    title, *body_lines = text.split("\n")
    starts = [number for number, line in enumerate(body_lines) if line.startswith(MESSAGE_START)]
    if not starts:
        return SplitThread(title, "", non_empty([joined(body_lines)]))
    ends = starts[1:] + [len(body_lines)]
    return SplitThread(
        title,
        joined(body_lines[: starts[0]]),
        [joined(body_lines[start:end]) for start, end in zip(starts, ends)],
    )


def joined(lines: list[str]) -> str:
    """The lines as one string, without blank lines at either end."""
    return "\n".join(lines).strip("\n")


def non_empty(pieces: list[str]) -> list[str]:
    return [piece for piece in pieces if piece]

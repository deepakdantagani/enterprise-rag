r"""GMAIL-1a: turn one raw Gmail thread into clean text. Pure: string in, CleanResult out.

Entry point:  clean_thread(raw) -> CleanResult(text, was_escaped)

27,870 of the 121,390 threads were saved as a JSON string, so a line break is the two
characters `\` and `n` and `From:` never sits at the start of a line. The Confluence
pipeline already detects and decodes exactly that (`is_escaped`, `unescape`), so both are
reused unchanged. What is not reused is `normalize`: it runs `fix_structure`, which would
turn the attachment bullet `- draft_transfer_annex_notes.docx` into a `##` heading. Gmail
gets a whitespace-only tidy instead.

The 179 threads that hold a literal `\n` but are not flagged come back untouched; which of
them are damage is GMAIL-1b's rule.

    >>> clean_thread("Notes\\n\\nFrom: Ana\\n- one\\n- two\\n- three\\n")
    CleanResult(text='Notes\n\nFrom: Ana\n- one\n- two\n- three\n', was_escaped=True)
    >>> clean_thread("Title  \n\n\n\nBody")
    CleanResult(text='Title\n\nBody\n', was_escaped=False)
"""
import re

from pipeline.cleaning import CleanResult, is_escaped, unescape

CARRIAGE_RETURN_LINE_BREAK = re.compile(r"\r\n?")
TRAILING_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)
BLANK_LINE_RUN = re.compile(r"\n{3,}")


def clean_thread(raw: str) -> CleanResult:
    """Unescape the thread if it was saved escaped, then tidy its whitespace."""
    was_escaped = is_escaped(raw)
    text = unescape(raw) if was_escaped else raw
    return CleanResult(text=tidy_whitespace(text), was_escaped=was_escaped)


def tidy_whitespace(text: str) -> str:
    r"""Line feeds only, no trailing spaces, one blank line at most, one final newline.

    >>> tidy_whitespace("a  \r\n\r\n\r\n\r\nb\n\n")
    'a\n\nb\n'
    >>> tidy_whitespace("  \n")
    ''
    """
    if not text.strip():
        return ""
    text = CARRIAGE_RETURN_LINE_BREAK.sub("\n", text)
    text = TRAILING_WHITESPACE.sub("", text)
    text = BLANK_LINE_RUN.sub("\n\n", text)
    return text.strip("\n") + "\n"

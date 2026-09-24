r"""SLACK-1: turn a JSON-escaped Slack thread back into real characters.

8,334 of the 285,605 threads were saved as a JSON string: after line 1 and a blank line,
the whole body sits on one line, with the two characters `\` `n` where each line break
belongs. Message splitting needs real line breaks, so this puts them back.

Only those files are touched. 9,637 other threads also contain a literal `\n`, but there it
means itself (an SSE capture, a printf inside a code block), so they come back unchanged.

Pure: text in, UnescapeResult out. No files, no events; the caller (SLACK-4) does both.

    >>> unescape('general\n\nLena: Poll \\"WFH\\"\\nRaj: ok')
    UnescapeResult(text='general\n\nLena: Poll "WFH"\nRaj: ok', rules_fired={'quote': 2, 'newline': 1})
    >>> unescape("eng\n\npaul: ```data\\n```\n\nkai: ok").rules_fired
    {}
"""
import re
from collections import Counter
from dataclasses import dataclass

ESCAPES = {  # as written in the file -> (rule name, the real character)
    r"\n": ("newline", "\n"),
    r"\"": ("quote", '"'),
    r"\t": ("tab", "\t"),
    r"\r": ("carriage_return", "\r"),
    r"\\": ("backslash", "\\"),
    r"\/": ("slash", "/"),
}
UNICODE_RULE = "unicode"
HEX = "[0-9a-fA-F]"
SURROGATE_PAIR = rf"\\u[dD][89abAB]{HEX}{{2}}\\u[dD][c-fC-F]{HEX}{{2}}"  # \ud83d\ude00: one emoji
NOT_A_SURROGATE = rf"\\u(?![dD][89a-fA-F]){HEX}{{4}}"                  # \u2014: one character
# A lone surrogate (\ud83d with no partner) is left as written: it has no character of its
# own and could not be written out as UTF-8.
UNICODE_ESCAPE = f"{SURROGATE_PAIR}|{NOT_A_SURROGATE}"
# A \n that is not the tail of an escaped backslash: `\\n` is a backslash and an n.
UNESCAPED_NEWLINE = re.compile(r"(?<!\\)(?:\\\\)*\\n")
ESCAPE_PATTERN = re.compile(
    "|".join(re.escape(escape) for escape in ESCAPES) + "|" + UNICODE_ESCAPE
)


@dataclass(frozen=True)
class UnescapeResult:
    text: str
    rules_fired: dict[str, int]  # rule name -> times it changed something; empty if untouched


def unescape(text: str) -> UnescapeResult:
    """Decode every escape in one left-to-right pass, but only if the thread is escaped."""
    if not is_escaped(text):
        return UnescapeResult(text, {})
    rules_fired = Counter()

    def decode(match: re.Match) -> str:
        rule_name, character = decode_escape(match.group())
        rules_fired[rule_name] += 1
        return character

    return UnescapeResult(ESCAPE_PATTERN.sub(decode, text), dict(rules_fired))


def is_escaped(text: str) -> bool:
    r"""True when the body (after the first blank line) is one line holding a literal \n.

    >>> is_escaped("general\n\nLena: hi\\nCarlos: yo"), is_escaped("general\n\nLena: hi\n\nCarlos: yo")
    (True, False)
    """
    body = text.split("\n\n", 1)[-1].rstrip("\n")
    return "\n" not in body and UNESCAPED_NEWLINE.search(body) is not None


def decode_escape(escape: str) -> tuple[str, str]:
    r"""One escape as written -> (rule name, real character).

    >>> decode_escape(r"\\"), decode_escape(r"\u00e9"), decode_escape(r"\ud83d\ude00")
    (('backslash', '\\'), ('unicode', 'é'), ('unicode', '😀'))
    """
    if escape in ESCAPES:
        return ESCAPES[escape]
    code_units = [int(hex_digits, 16) for hex_digits in escape.split("\\u")[1:]]
    utf16 = "".join(map(chr, code_units)).encode("utf-16-le", "surrogatepass")
    return UNICODE_RULE, utf16.decode("utf-16-le")

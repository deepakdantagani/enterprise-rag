"""GMAIL-4: read the header lines at the top of one message block.

Only known header names count as headers, so a body line such as "Attachments: plan.pdf"
stays in the body for GMAIL-7. The date is returned as written; GMAIL-5 parses it.
"""
import re
from dataclasses import dataclass

HEADER_LINE = re.compile(r"^([A-Za-z][A-Za-z-]*):[ \t]?(.*)$")
USED_KEYS = {"from", "to", "cc", "date", "sent", "subject"}
IGNORED_KEYS = {"bcc", "reply-to", "references"}
HEADER_KEYS = USED_KEYS | IGNORED_KEYS


@dataclass(frozen=True)
class ParsedHeaders:
    from_: str
    to: list[str]
    cc: list[str]
    date_raw: str
    subject: str
    body: str


def parse_headers(block: str) -> ParsedHeaders:
    entries, body_lines = read_header_entries(block.split("\n"))
    first = first_value_per_key(entries)
    return ParsedHeaders(
        from_=first.get("from", ""),
        to=split_addresses(first.get("to", "")),
        cc=split_addresses(first.get("cc", "")),
        date_raw=first.get("date") or first.get("sent", ""),
        subject=first.get("subject", ""),
        body="\n".join(body_lines).strip("\n"),
    )


def read_header_entries(lines: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Return the (key, value) header lines from the top, and the lines left over."""
    entries: list[list[str]] = []
    position = 0
    while position < len(lines):
        line = lines[position]
        if entries and is_wrapped_continuation(line):
            entries[-1][1] += " " + line.strip()
        else:
            match = HEADER_LINE.match(line)
            if not match or match[1].lower() not in HEADER_KEYS:
                break
            entries.append([match[1].lower(), match[2].strip()])
        position += 1
    return [(key, value) for key, value in entries], lines[position:]


def is_wrapped_continuation(line: str) -> bool:
    return line[:1] in (" ", "\t") and bool(line.strip())


def first_value_per_key(entries: list[tuple[str, str]]) -> dict[str, str]:
    first: dict[str, str] = {}
    for key, value in entries:
        first.setdefault(key, value)
    return first


def split_addresses(value: str) -> list[str]:
    """Split on commas outside angle brackets; a name with a comma splits into two pieces."""
    pieces, current, depth = [], "", 0
    for char in value:
        depth += char == "<"
        depth -= char == ">"
        if char == "," and depth == 0:
            pieces.append(current)
            current = ""
        else:
            current += char
    pieces.append(current)
    return [piece.strip() for piece in pieces if piece.strip()]

"""GMAIL-5a: turn one Gmail date text in the ISO or RFC 2822 shape into a UTC instant.

The standard library alone is not enough: `email.utils.parsedate_to_datetime` returns a wrong,
zone-less time without an error for "-07:00" (colon in the offset), so that case is handled
here. Other shapes (Gmail's display style, named zones) are GMAIL-5b and raise for now.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RFC_2822 = re.compile(
    r"^(?:[A-Za-z]{3}, )?\d{1,2} [A-Za-z]{3} \d{4} \d{1,2}:\d\d(?::\d\d)? [+-]\d\d:?\d\d$"
)
OFFSET_WITH_COLON = re.compile(r"([+-]\d\d):(\d\d)$")
TRAILING_NOISE = re.compile(r"(?:\s*\\r|\s*\([^)]*\))+$")  # a literal \r left by escaping, or "(PST)"


@dataclass(frozen=True)
class NormalisedDate:
    sent_at: str
    utc_offset_minutes: int | None
    assumed_utc: bool
    rule: str


def normalise_date(raw: str) -> NormalisedDate:
    text = TRAILING_NOISE.sub("", raw.strip())
    for read in (read_iso, read_rfc_2822):
        try:
            result = read(text)
        except ValueError as error:
            raise ValueError(f"unreadable date {raw!r}: {error}") from error
        if result:
            return result
    raise ValueError(f"unrecognised date: {raw!r}")


def read_iso(text: str) -> NormalisedDate | None:
    if ":" not in text:  # fromisoformat would accept a bare date and invent midnight
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return build("iso", parsed, offset_minutes=None, assumed_utc=True)
    return build("iso", parsed.replace(tzinfo=None), offset_minutes_of(parsed), assumed_utc=False)


def read_rfc_2822(text: str) -> NormalisedDate | None:
    if not RFC_2822.match(text):
        return None
    parsed = parsedate_to_datetime(OFFSET_WITH_COLON.sub(r"\1\2", text))
    if parsed.tzinfo is None:  # "-0000": UTC, but the sender's own zone is unknown
        return build("rfc2822", parsed, offset_minutes=None, assumed_utc=False)
    return build("rfc2822", parsed.replace(tzinfo=None), offset_minutes_of(parsed), assumed_utc=False)


def offset_minutes_of(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)


def build(rule: str, local: datetime, offset_minutes: int | None, assumed_utc: bool) -> NormalisedDate:
    utc = (local - timedelta(minutes=offset_minutes or 0)).replace(tzinfo=timezone.utc)
    return NormalisedDate(utc.isoformat(), offset_minutes, assumed_utc, rule)

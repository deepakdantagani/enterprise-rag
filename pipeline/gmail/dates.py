"""GMAIL-5a and 5b: turn one Gmail date text into a UTC instant, the sender's offset and a flag.

Three rules are tried in order: ISO, RFC 2822, then the looser Gmail display style. The
standard library alone is not enough: for "-07:00" (colon) or "4:40 PM" it returns a
wrong time without an error, so the second and third rules are written out here.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

RFC_2822 = re.compile(
    r"^(?:[A-Za-z]{3}, )?\d{1,2} [A-Za-z]{3} \d{4} \d{1,2}:\d\d(?::\d\d)? [+-]\d\d:?\d\d$"
)
OFFSET_WITH_COLON = re.compile(r"([+-]\d\d):(\d\d)$")
TRAILING_NOISE = re.compile(r"(?:\s*\\r|\s*\([^)]*\))+$")  # a literal \r left by escaping, or "(PST)"

LOOSE = re.compile(
    r"^(?:(?P<weekday>[A-Za-z]{3,9}),?\s+)?"
    r"(?:(?P<iso_year>\d{4})-(?P<iso_month>\d\d)-(?P<iso_day>\d\d)"
    r"|(?P<mf_month>[A-Za-z]{3,9}) (?P<mf_day>\d{1,2}),? (?P<mf_year>\d{4})"
    r"|(?P<df_day>\d{1,2}) (?P<df_month>[A-Za-z]{3,9}) (?P<df_year>\d{4}))"
    r"(?:\s+at)?\s+(?P<hour>\d{1,2}):(?P<minute>\d\d)(?::(?P<second>\d\d))?(?:\s*(?P<am_pm>[AP]M))?"
    r"(?:\s+(?P<zone>[+-]\d\d:?\d\d|[A-Z]{2,4}))?$"
)
DATE_PREFIXES = ("iso", "mf", "df")

MONTH_NAMES = "january february march april may june july august september october november december".split()
MONTH_NUMBERS = {spelling: number for number, name in enumerate(MONTH_NAMES, 1) for spelling in (name, name[:3])}
MONTH_NUMBERS["sept"] = 9
WEEKDAY_NAMES = "monday tuesday wednesday thursday friday saturday sunday".split()
WEEKDAY_SPELLINGS = set(WEEKDAY_NAMES) | {name[:3] for name in WEEKDAY_NAMES}

# Zone names seen in the corpus. BST is read as British and IST as India (20 blocks between them).
NAMED_OFFSET_MINUTES = {
    "UTC": 0, "GMT": 0, "BST": 60, "CET": 60, "CEST": 120, "IST": 330, "SGT": 480, "JST": 540,
    "PST": -480, "PDT": -420, "CDT": -300, "EST": -300, "EDT": -240,
}
# PT and ET switch between summer and winter time, so the date decides.
REGIONAL_ZONES = {"PT": "America/Los_Angeles", "ET": "America/New_York"}


@dataclass(frozen=True)
class NormalisedDate:
    sent_at: str
    utc_offset_minutes: int | None
    assumed_utc: bool
    rule: str


def normalise_date(raw: str) -> NormalisedDate:
    text = TRAILING_NOISE.sub("", raw.strip())
    for read in (read_iso, read_rfc_2822, read_loose):
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


def read_loose(text: str) -> NormalisedDate | None:
    match = LOOSE.match(text)
    if not match or not is_weekday(match["weekday"]):
        return None
    local = local_time(match)
    zone = match["zone"]
    if zone is None:
        return build("loose", local, offset_minutes=None, assumed_utc=True)
    return build("loose", local, zone_offset_minutes(zone, local), assumed_utc=False)


def is_weekday(word: str | None) -> bool:
    return word is None or word.lower() in WEEKDAY_SPELLINGS


def local_time(match: re.Match) -> datetime:
    prefix = next(p for p in DATE_PREFIXES if match[f"{p}_year"])
    return datetime(
        int(match[f"{prefix}_year"]),
        month_number(match[f"{prefix}_month"]),
        int(match[f"{prefix}_day"]),
        hour_of(match),
        int(match["minute"]),
        int(match["second"] or 0),
    )


def month_number(text: str) -> int:
    if text.isdigit():
        return int(text)
    if text.lower() not in MONTH_NUMBERS:
        raise ValueError(f"unknown month name: {text}")
    return MONTH_NUMBERS[text.lower()]


def hour_of(match: re.Match) -> int:
    hour, am_pm = int(match["hour"]), match["am_pm"]
    if am_pm is None or hour > 12 or hour == 0:  # "13:56 PM", "00:30 PM": already 24-hour, the PM is noise
        return hour
    return hour % 12 + (12 if am_pm == "PM" else 0)


def zone_offset_minutes(zone: str, local: datetime) -> int:
    if zone[0] in "+-":
        return signed_minutes(zone)
    if zone in NAMED_OFFSET_MINUTES:
        return NAMED_OFFSET_MINUTES[zone]
    if zone in REGIONAL_ZONES:
        return offset_minutes_of(local.replace(tzinfo=ZoneInfo(REGIONAL_ZONES[zone])))
    raise ValueError(f"unknown zone name: {zone}")


def signed_minutes(offset: str) -> int:
    digits = offset[1:].replace(":", "")
    minutes = int(digits[:2]) * 60 + int(digits[2:])
    return -minutes if offset[0] == "-" else minutes


def offset_minutes_of(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)


def build(rule: str, local: datetime, offset_minutes: int | None, assumed_utc: bool) -> NormalisedDate:
    utc = (local - timedelta(minutes=offset_minutes or 0)).replace(tzinfo=timezone.utc)
    return NormalisedDate(utc.isoformat(), offset_minutes, assumed_utc, rule)

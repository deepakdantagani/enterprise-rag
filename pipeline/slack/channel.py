"""SLACK-5: which channel a clean Slack thread belongs to, and how we know.

Three routes, tried in order (ROUTES). The first that finds a known channel wins:

    line1        line 1 is the channel itself            'customer-success'       273,519 threads
    export_path  line 1 is the export path that held it  'sources/slack/eng-ml/…' 943
    unknown      neither                                 '1719998880'             11,143

Only the 36 channels in KNOWN_CHANNELS count. SLACK-0 found 130 channel-shaped words on
line 1; the other 94 each name one thread and match its own slug (`kv-residency-sim-harness-sync`),
so they are topics, not channels. A channel named further down a thread is a mention, not
where the thread lives, so only line 1 is read.

Pure: the text of one clean thread (SLACK-4's output) in, Channel out.

    >>> channel_of("incidents\\n\\nkai: paging\\n")
    Channel(name='incidents', route='line1')
"""
import re
from collections.abc import Callable
from typing import NamedTuple

KNOWN_CHANNELS = frozenset({  # every channel on line 1 of 3 or more threads (SLACK-0 profile)
    "all-hands", "announcements", "architecture", "customer-success", "design", "devex",
    "docs", "eng", "eng-infra", "eng-ml", "eng-oncall", "eng-platform", "eng-releases",
    "eng-runtime", "eng-security", "eng-sre", "finance", "general", "help", "incidents",
    "lunch-plans", "marketing", "memes", "new-hires", "partnerships", "people-ops",
    "postmortems", "product", "random", "release-war-room", "sales", "sales-poc-benchmark",
    "sports", "support", "vendors", "watercooler",
})
EXPORT_PATH = re.compile(r"sources/slack/([^/\s]+)/")
UNKNOWN = "unknown"


class Channel(NamedTuple):
    name: str   # one of KNOWN_CHANNELS, or "unknown"
    route: str  # the ROUTES entry that found it, or "unknown"


def channel_of(text: str) -> Channel:
    """The first route that names a known channel, else unknown."""
    first_line = text.split("\n", 1)[0].strip()
    for route, find_channel in ROUTES:
        name = find_channel(first_line)
        if name in KNOWN_CHANNELS:
            return Channel(name, route)
    return Channel(UNKNOWN, UNKNOWN)


def channel_on_line1(first_line: str) -> str:
    return first_line


def channel_in_export_path(first_line: str) -> str | None:
    """'sources/slack/eng-ml/3312349999-photon9b-….json' -> 'eng-ml'."""
    match = EXPORT_PATH.match(first_line)
    return match.group(1) if match else None


ROUTES: tuple[tuple[str, Callable[[str], str | None]], ...] = (  # (route name, finder), in order
    ("line1", channel_on_line1),
    ("export_path", channel_in_export_path),
)

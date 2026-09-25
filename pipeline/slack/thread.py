"""SLACK-8: one clean Slack thread file -> one Thread record.

Glue, no new rules: the file name gives the id and slug, `channel_of` (SLACK-5) the channel,
`split_messages` (SLACK-6) the header and messages, `parse_speaker` (SLACK-7) each speaker.

The file name is `dsid_<32 hex>__<timestamp>[-<slug>].txt`. The dsid is unique across all
285,605 files, so it is the id. The timestamp is dropped: it is not a time (keyboard walks,
years 2001 to 2513; design section 5), and a field would invite someone to rank on it.
6,199 names have no slug.

Nothing is lost: `header + "".join(m.text for m in messages)` is the text, byte for byte.

Pure: file name and text in, Thread out. The caller reads the file.

    >>> thread = parse_thread("dsid_a4e702bd03254699b0e7bed0000972ab__1793045678-novacare-vra-check.txt",
    ...                       "customer-success\\n\\nAisha (CS): Hey team\\n")
    >>> thread.doc_id, thread.slug, thread.channel.name, thread.participants
    ('a4e702bd03254699b0e7bed0000972ab', 'novacare-vra-check', 'customer-success', ['Aisha'])
"""
import re
from typing import NamedTuple, Optional

from pipeline.slack.channel import Channel, channel_of
from pipeline.slack.messages import split_messages
from pipeline.slack.speaker import Speaker, parse_speaker

THREAD_FILE_NAME = re.compile(
    r"dsid_(?P<doc_id>[0-9a-f]{32})"  # the id
    r"__\d+(?:_\d+)?"                 # the timestamp, not kept: 2987654321, 1859999999_1
    r"(?:-?(?P<slug>.+))?\.txt"       # -novacare-vra-check; nothing; 1 name lacks the dash
)


class Message(NamedTuple):
    turn: int         # 0 for the first message in the thread
    speaker: Speaker
    text: str         # the whole message, speaker line included, with its own line breaks


class Thread(NamedTuple):
    doc_id: str
    slug: Optional[str]
    channel: Channel
    header: str               # text before the first message
    messages: list[Message]
    participants: list[str]   # distinct speaker names, in the order they first speak


def parse_thread(file_name: str, text: str) -> Thread:
    """The record for one clean thread file."""
    doc_id, slug = id_and_slug(file_name)
    split = split_messages(text)
    messages = [Message(turn, parse_speaker(message), message) for turn, message in enumerate(split.messages)]
    return Thread(doc_id, slug, channel_of(text), split.header, messages, participants(messages))


def id_and_slug(file_name: str) -> tuple[str, Optional[str]]:
    """doc_id and slug from a thread's file name; ValueError if it is not one.

    >>> id_and_slug("dsid_5badc87efd7a49128d67b0234f809fa1__2987654321.txt")
    ('5badc87efd7a49128d67b0234f809fa1', None)
    """
    match = THREAD_FILE_NAME.fullmatch(file_name)
    if match is None:
        raise ValueError(f"not a Slack thread file name: {file_name!r}")
    return match["doc_id"], match["slug"]


def participants(messages: list[Message]) -> list[str]:
    """Each speaker's name once, in the order they first speak."""
    return list(dict.fromkeys(message.speaker.name for message in messages))

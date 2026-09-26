r"""GMAIL-8: one clean thread becomes one flat record per message.

Joins split_messages (3), parse_headers (4), normalise_date (5), strip_quotes (6) and
attachment_names (7a). The thread fields come from the file name and line 1, the rest from
the message. Nothing is invented: a message with no readable date gets an empty `sent_at`
and `date_missing`, and `date_raw` keeps the text, so an unreadable date (126) can be told
from an absent one (1,243). Text before the first `From:` (609 threads, GMAIL-3b) is in no
record. `sha256` is of the message block as split_messages returns it, so a change to
clean_thread changes it.

    >>> name = "dsid_" + "0" * 32 + "__20260625-payment-orchestration.txt"
    >>> record, = message_records(name, "Title\n\nFrom: A <a@x.com>\nDate: 2026-06-25 09:12 -0700\n\nHi\n")
    >>> record.message_index, record.sent_at, record.date_raw, record.body
    (0, '2026-06-25T16:12:00+00:00', '2026-06-25 09:12 -0700', 'Hi')
"""
import hashlib
import re
from dataclasses import dataclass

from pipeline.gmail.attachments import attachment_names
from pipeline.gmail.dates import normalise_date
from pipeline.gmail.headers import parse_headers
from pipeline.gmail.messages import split_messages
from pipeline.gmail.quotes import strip_quotes

FILE_NAME = re.compile(r"^(?P<dsid>dsid_[0-9a-f]{32})__(?P<thread_date>\d{8})-")


@dataclass(frozen=True)
class MessageRecord:
    dsid: str
    thread_title: str
    thread_date: str
    message_index: int
    sender: str
    recipients: list[str]
    sent_at: str
    date_raw: str
    subject: str
    attachments: list[str]
    body: str
    sha256: str
    headers_missing: bool
    date_missing: bool
    date_assumed_utc: bool
    body_empty: bool


def message_records(filename: str, text: str) -> list[MessageRecord]:
    name = FILE_NAME.match(filename)
    if not name:
        raise ValueError(f"not a Gmail thread file name: {filename!r}")
    thread = split_messages(text)
    return [
        message_record(name["dsid"], name["thread_date"], thread.title, index, block)
        for index, block in enumerate(thread.blocks)
    ]


def message_record(dsid: str, thread_date: str, thread_title: str, index: int, block: str) -> MessageRecord:
    headers = parse_headers(block)
    body = strip_quotes(headers.body).text
    sent_at, assumed_utc = read_sent_at(headers.date_raw)
    return MessageRecord(
        dsid=dsid,
        thread_title=thread_title,
        thread_date=thread_date,
        message_index=index,
        sender=headers.from_,
        recipients=headers.to + headers.cc,
        sent_at=sent_at,
        date_raw=headers.date_raw,
        subject=headers.subject,
        attachments=attachment_names(body),
        body=body,
        sha256=hashlib.sha256(block.encode("utf-8")).hexdigest(),
        headers_missing=not (headers.from_ or headers.to or headers.cc or headers.date_raw or headers.subject),
        date_missing=not sent_at,
        date_assumed_utc=assumed_utc,
        body_empty=not body.strip(),
    )


def read_sent_at(date_raw: str) -> tuple[str, bool]:
    """The UTC time and whether UTC was assumed; ("", False) when there is no readable date."""
    try:
        date = normalise_date(date_raw)
    except ValueError:
        return "", False
    return date.sent_at, date.assumed_utc

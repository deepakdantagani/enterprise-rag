"""SLACK-4: clean every Slack thread once into data/slack/clean/, with a manifest beside it.

The only module of the Slack cleaning stage that touches disk. SLACK-1 (unescape) and
SLACK-2 (normalize_whitespace) stay pure; this reads the zips, runs both, writes each clean
thread under its own name, and writes `_manifest.json`: one row per file with the sha256 of
the raw and clean bytes and the rules that fired.

    zips --read--> clean_thread() --write--> clean/<name>.txt
                         |
                         +--> manifest_row() --> clean/_manifest.json

Every file is an event on the shared dispatcher (SLACK-3): FileCleaned, or FileFailed and
the run goes on. One StageDone closes the run. Observing never changes the output.

Run: uv run python -m pipeline.slack.corpus
"""
import hashlib
import json
import sys
import time
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

from pipeline.observability import FileCleaned, FileFailed, StageDone, dispatcher, events_logged_to
from pipeline.slack.unescape import unescape
from pipeline.slack.whitespace import normalize_whitespace

SOURCE = "slack"
STAGE = "clean"
MANIFEST_NAME = "_manifest.json"


@dispatcher.span
def write_clean_corpus(archives_dir: Path, clean_dir: Path) -> list[dict]:
    """Clean every thread in the zips into clean_dir, save the manifest, return its rows.

    One span covers the stage; every event inside it carries that span_id."""
    started, failed, rows = time.monotonic(), 0, []
    clean_dir.mkdir(parents=True, exist_ok=True)
    for name, raw_bytes in read_threads(archives_dir):
        try:
            row = clean_one_thread(name, raw_bytes, clean_dir)
        except (UnicodeDecodeError, OSError) as error:
            failed += 1
            dispatcher.event(FileFailed(source=SOURCE, file=name, error_type=type(error).__name__,
                                        message=str(error)))
            continue
        rows.append(row)
    rows.sort(key=lambda row: row["name"])
    save_manifest(clean_dir, rows)
    dispatcher.event(StageDone(source=SOURCE, stage=STAGE, files=len(rows), failed=failed,
                               seconds=round(time.monotonic() - started, 1)))
    return rows


def read_threads(archives_dir: Path) -> Iterator[tuple[str, bytes]]:
    """(file name, raw bytes) for every .txt in every zip, zips in name order, without unzipping."""
    for archive_path in sorted(archives_dir.glob("*.zip")):
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                if member.endswith(".txt"):
                    yield Path(member).name, archive.read(member)


def clean_one_thread(name: str, raw_bytes: bytes, clean_dir: Path) -> dict:
    """Clean one thread, write it, emit FileCleaned, return its manifest row."""
    text, rules = clean_thread(raw_bytes.decode("utf-8"))
    clean_bytes = text.encode("utf-8")
    (clean_dir / name).write_bytes(clean_bytes)
    dispatcher.event(FileCleaned(source=SOURCE, file=name, rules_fired=rules,
                                 bytes_in=len(raw_bytes), bytes_out=len(clean_bytes)))
    return manifest_row(name, raw_bytes, clean_bytes, rules)


def clean_thread(raw: str) -> tuple[str, dict[str, int]]:
    """SLACK-1 then SLACK-2. SLACK-1's rules get an `unescape_` prefix: both stages have a
    `carriage_return` rule, and they mean different things."""
    unescaped = unescape(raw)
    normalized = normalize_whitespace(unescaped.text)
    rules = {f"unescape_{rule}": count for rule, count in unescaped.rules_fired.items()}
    return normalized.text, rules | normalized.rules_fired


def manifest_row(name: str, raw_bytes: bytes, clean_bytes: bytes, rules: dict[str, int]) -> dict:
    return {
        "name": name,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "clean_sha256": hashlib.sha256(clean_bytes).hexdigest(),
        "rules": rules,
    }


def save_manifest(clean_dir: Path, rows: list[dict]) -> None:
    """A JSON list with one row per line, so a diff of two runs shows the files that changed."""
    lines = ",\n".join(json.dumps(row) for row in rows)
    (clean_dir / MANIFEST_NAME).write_text(f"[\n{lines}\n]\n", encoding="utf-8")


if __name__ == "__main__":
    slack_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/slack")
    log_path = slack_dir / "logs" / f"clean-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.jsonl"
    with events_logged_to(log_path):
        rows = write_clean_corpus(slack_dir / "archives", slack_dir / "clean")
    print(f"{len(rows)} threads cleaned; log: {log_path}")

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
import shutil
import sys
import time
import uuid
import zipfile
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path

from pipeline.observability import FileCleaned, FileFailed, StageDone, dispatcher, events_logged_to
from pipeline.slack.unescape import unescape
from pipeline.slack.whitespace import normalize_whitespace

SOURCE = "slack"
STAGE = "clean"
MANIFEST_NAME = "_manifest.json"
STAGING_SUFFIX = ".staging"


@dispatcher.span
def write_clean_corpus(archives_dir: Path, clean_dir: Path) -> list[dict]:
    """Clean every thread in the zips into clean_dir, save the manifest, return its rows.

    Everything is written to a fresh folder that replaces clean_dir only at the end, so
    clean_dir never mixes two runs, and always holds exactly the files its manifest lists.
    One span covers the stage; every event inside it carries that span_id."""
    started, failed, rows, seen = time.monotonic(), 0, [], set()
    staging_dir = fresh_dir(clean_dir.with_name(clean_dir.name + STAGING_SUFFIX))
    for name, read_raw_bytes in read_threads(archives_dir):
        if name in seen:  # the first one stays; this one would overwrite it
            failed += report_failure(name, DuplicateName(f"{name} appears more than once in the zips"))
            continue
        seen.add(name)
        try:
            rows.append(clean_one_thread(name, read_raw_bytes(), staging_dir))
        except READ_ERRORS as error:
            (staging_dir / name).unlink(missing_ok=True)  # no half-written file without a row
            failed += report_failure(name, error)
    rows.sort(key=lambda row: row["name"])
    save_manifest(staging_dir, rows)
    replace_dir(clean_dir, staging_dir)
    dispatcher.event(StageDone(source=SOURCE, stage=STAGE, files=len(rows), failed=failed,
                               seconds=round(time.monotonic() - started, 1)))
    return rows


class DuplicateName(Exception):
    """Two zip members share a file name; the second would overwrite the first."""


# Bad data fails one file; anything else is a bug in the cleaners and stops the run.
READ_ERRORS = (UnicodeDecodeError, zipfile.BadZipFile, OSError)


def report_failure(name: str, error: Exception) -> int:
    """Emit FileFailed for one file; returns 1, the number of failures to add."""
    dispatcher.event(FileFailed(source=SOURCE, file=name, error_type=type(error).__name__,
                                message=str(error)))
    return 1


def read_threads(archives_dir: Path) -> Iterator[tuple[str, Callable[[], bytes]]]:
    """(file name, a function that reads its raw bytes) for every .txt in every zip, zips in
    name order, without unzipping. Reading is deferred so a corrupt member fails as one file,
    and a corrupt zip as one entry named after the zip."""
    for archive_path in sorted(archives_dir.glob("*.zip")):
        try:
            archive = zipfile.ZipFile(archive_path)
        except zipfile.BadZipFile as error:
            yield archive_path.name, partial(raise_error, error)
            continue
        with archive:
            for member in archive.namelist():
                if member.endswith(".txt"):
                    yield Path(member).name, partial(archive.read, member)


def raise_error(error: Exception) -> bytes:
    raise error


def fresh_dir(path: Path) -> Path:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def replace_dir(target: Path, replacement: Path) -> None:
    """Swap replacement in as target. The old target is derived data: this run rebuilt it."""
    shutil.rmtree(target, ignore_errors=True)
    replacement.rename(target)


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

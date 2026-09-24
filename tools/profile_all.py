r"""DATA-1: count what is in each source's archives and write data/<source>/profile.json.

Confluence, Gmail and Slack already have profiles built for them (Gmail and Slack know their
own structure). This gives every other source the same first look, counting only: files,
bytes, chars, lines and tokens (4 chars per token, nearest rank), empty files, repeated
dsids (the 32-hex id at the front of each file name), and files exported as one JSON
string (no real line break, but a literal `\n`).

Run: uv run python -m tools.profile_all linear fireflies github google_drive hubspot jira

    >>> percentiles([3, 1, 2])
    {'p50': 2, 'p90': 3, 'p99': 3, 'max': 3}
    >>> profile_files([("dsid_a__x.txt", b"a\nb"), ("dsid_a__y.txt", b"")])["duplicate_dsids"]
    1
"""
import json
import math
import sys
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

CHARS_PER_TOKEN = 4
PERCENTILES = (50, 90, 99)
DATA_DIR = Path("data")


def read_files(archives_dir: Path) -> Iterator[tuple[str, bytes]]:
    """Yield (file name, bytes) of every .txt in every zip, in a fixed order."""
    for zip_path in sorted(Path(archives_dir).glob("*.zip")):
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if name.endswith(".txt"):
                    yield Path(name).name, archive.read(name)


def percentiles(values: list[int]) -> dict:
    ordered = sorted(values)
    result = {f"p{p}": ordered[math.ceil(p / 100 * len(ordered)) - 1] for p in PERCENTILES}
    return {**result, "max": ordered[-1]}


def dsid_of(file_name: str) -> str:
    return file_name.split("__")[0]


def is_json_escaped(text: str) -> bool:
    return "\n" not in text.strip() and "\\n" in text


def profile_files(files: Iterable[tuple[str, bytes]]) -> dict:
    """Turn (name, bytes) pairs into the profile."""
    dsids, chars, lines, byte_sizes = set(), [], [], []
    duplicate_dsids = empty_files = escaped_files = 0
    for name, raw in files:
        text = raw.decode("utf-8")
        duplicate_dsids += dsid_of(name) in dsids
        dsids.add(dsid_of(name))
        empty_files += not text.strip()
        escaped_files += is_json_escaped(text)
        byte_sizes.append(len(raw))
        chars.append(len(text))
        lines.append(text.count("\n") + 1)
    return {
        "files": len(chars),
        "bytes": sum(byte_sizes),
        "empty_files": empty_files,
        "duplicate_dsids": duplicate_dsids,
        "json_escaped_files": escaped_files,
        "chars": percentiles(chars),
        "tokens": percentiles([n // CHARS_PER_TOKEN for n in chars]),
        "lines": percentiles(lines),
    }


def profile_source(source: str, data_dir: Path = DATA_DIR) -> dict:
    counts = profile_files(read_files(data_dir / source / "archives"))
    (data_dir / source / "profile.json").write_text(json.dumps(counts, indent=2) + "\n")
    return counts


if __name__ == "__main__":
    for source in sys.argv[1:]:
        counts = profile_source(source)
        print(source, counts["files"], counts["tokens"])

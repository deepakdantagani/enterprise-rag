r"""SLACK-0: count what is in the Slack corpus, straight from the 58 zips.

Every later Slack story quotes a number (how many threads, how long, which channels).
This writes those numbers to one file, data/slack/profile.json, so each one can be
reproduced. It only counts: it changes no file and decides no rule. Line 1 of a thread
is usually its channel, but 94 files carry a one-off topic name there
(`kv-residency-sim-harness-sync`); the profile lists every such word with its count and
leaves the channel rule to SLACK-5.

Run: uv run python -m tools.slack_profile

    >>> is_channel_shaped("customer-success"), is_channel_shaped("1719998880")
    (True, False)
    >>> first_line(" incidents \n\nmorgan: hi")
    'incidents'
    >>> token_summary([7, 5, 6])
    {'p50': 6, 'p90': 7, 'p99': 7, 'max': 7}
"""
import json
import math
import re
import sys
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

CHANNEL_NAME_PATTERN = re.compile(r"[a-z][a-z0-9-]*")
CHARS_PER_TOKEN = 4
TOKEN_PERCENTILES = (50, 90, 99)


def profile(archives_dir: Path, out_path: Path) -> dict:
    """Count the corpus in archives_dir, write the counts to out_path as JSON, return them."""
    counts = count_threads(read_thread_files(archives_dir))
    Path(out_path).write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def read_thread_files(archives_dir: Path) -> Iterator[bytes]:
    """Yield the raw bytes of every .txt inside every zip, in a fixed order, without unzipping."""
    for archive_path in sorted(Path(archives_dir).glob("*.zip")):
        with zipfile.ZipFile(archive_path) as archive:
            for file_name in archive.namelist():
                if file_name.endswith(".txt"):
                    yield archive.read(file_name)


def count_threads(thread_files: Iterable[bytes]) -> dict:
    """Turn raw thread files into the profile: sizes, token percentiles, line-1 words."""
    file_sizes, token_counts, first_line_counts = [], [], Counter()
    for raw_bytes in thread_files:
        text = raw_bytes.decode("utf-8")
        file_sizes.append(len(raw_bytes))
        token_counts.append(len(text) // CHARS_PER_TOKEN)
        first_line_counts[first_line(text)] += 1
    channel_shaped_words = {
        word: file_count
        for word, file_count in first_line_counts.items()
        if is_channel_shaped(word)
    }
    return {
        "files": len(file_sizes),
        "bytes": sum(file_sizes),
        "tokens": token_summary(token_counts),
        "line1_channel_shaped": most_common_first(channel_shaped_words),
        "line1_other": len(file_sizes) - sum(channel_shaped_words.values()),
    }


def first_line(text: str) -> str:
    """Line 1 with surrounding spaces removed: where the export usually puts the channel."""
    return text.split("\n", 1)[0].strip()


def is_channel_shaped(word: str) -> bool:
    """Lowercase letters, digits and dashes, starting with a letter: how channels are named."""
    return CHANNEL_NAME_PATTERN.fullmatch(word) is not None


def token_summary(token_counts: list[int]) -> dict:
    """p50, p90, p99 and max of the per-thread token counts."""
    ascending = sorted(token_counts)
    summary = {f"p{p}": percentile(ascending, p) for p in TOKEN_PERCENTILES}
    return summary | {"max": ascending[-1]}


def percentile(ascending_values: list[int], p: int) -> int:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it."""
    return ascending_values[math.ceil(p / 100 * len(ascending_values)) - 1]


def most_common_first(word_counts: dict[str, int]) -> dict[str, int]:
    """Sort by count, largest first, then by word, so the JSON is identical on every run."""
    return dict(sorted(word_counts.items(), key=lambda item: (-item[1], item[0])))


if __name__ == "__main__":
    slack_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/slack")
    counts = profile(slack_dir / "archives", slack_dir / "profile.json")
    print(json.dumps(counts, indent=2)[:400])

r"""GMAIL-0: count what is in the Gmail corpus, straight from the raw exports.

Every later Gmail story quotes a number (how many threads, how many are escaped, how
many have no From: line). This writes those numbers to one file, data/gmail/profile.json,
so each one can be reproduced. It only counts: it changes no file and decides no rule.
In particular it does not split messages, parse headers or strip quotes — those are
GMAIL-3, GMAIL-4 and GMAIL-6's decisions. A file with a literal backslash-n is only
listed as escaped or ambiguous; which of the ambiguous ones are real damage (as
opposed to a printf string) is GMAIL-1's rule, not this one's.

Run: uv run python -m tools.gmail_profile

    >>> has_line_starting_with("From: a\n\nBody", "From:")
    True
    >>> has_line_starting_with("Subject: From: a workaround", "From:")
    False
    >>> token_summary([7, 5, 6])
    {'p50': 6, 'p90': 7, 'p99': 7, 'max': 7}
"""
import json
import math
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from pipeline.cleaning import is_escaped

CHARS_PER_TOKEN = 4
TOKEN_PERCENTILES = (50, 90, 99)
_LINE_SPLIT = re.compile(r"\n|\\n")  # a real newline or a literal (escaped) one


def profile(raw_dir: Path, out_path: Path) -> dict:
    """Count the corpus in raw_dir, write the counts to out_path as JSON, return them."""
    counts = count_threads(read_thread_files(raw_dir))
    Path(out_path).write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def read_thread_files(raw_dir: Path) -> Iterator[bytes]:
    """Yield the raw bytes of every .txt in raw_dir, in a fixed (file-name) order."""
    for path in sorted(Path(raw_dir).glob("*.txt")):
        yield path.read_bytes()


def count_threads(thread_files: Iterable[bytes]) -> dict:
    """Turn raw thread files into the profile: sizes, token percentiles, escape and From: counts."""
    file_sizes, token_counts = [], []
    literal_escape_files = is_escaped_files = no_from_files = 0
    for raw_bytes in thread_files:
        text = raw_bytes.decode("utf-8")
        file_sizes.append(len(raw_bytes))
        token_counts.append(len(text) // CHARS_PER_TOKEN)
        if "\\n" in text:
            literal_escape_files += 1
        if is_escaped(text):
            is_escaped_files += 1
        if not has_line_starting_with(text, "From:"):
            no_from_files += 1
    return {
        "files": len(file_sizes),
        "bytes": sum(file_sizes),
        "tokens": token_summary(token_counts),
        "literal_escape_files": literal_escape_files,
        "is_escaped_files": is_escaped_files,
        "ambiguous_escape_files": literal_escape_files - is_escaped_files,
        "no_from_files": no_from_files,
    }


def has_line_starting_with(text: str, prefix: str) -> bool:
    r"""True when some line, real or escaped ("\n" as two characters), starts with prefix.

    A thread's headers can survive on an escaped line just like a real one, and
    From: can appear mid-sentence in prose without being a header, so both must be
    checked and only a line start counts.

    Input -> output:
        >>> has_line_starting_with("Title\nFrom: a <a@b.com>", "From:")
        True
        >>> has_line_starting_with("Title\\nFrom: a <a@b.com>", "From:")
        True
        >>> has_line_starting_with("please see the From: field below", "From:")
        False
    """
    return any(line.strip().startswith(prefix) for line in _LINE_SPLIT.split(text))


def token_summary(token_counts: list[int]) -> dict:
    """p50, p90, p99 and max of the per-thread token counts."""
    ascending = sorted(token_counts)
    summary = {f"p{p}": percentile(ascending, p) for p in TOKEN_PERCENTILES}
    return summary | {"max": ascending[-1]}


def percentile(ascending_values: list[int], p: int) -> int:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it."""
    return ascending_values[math.ceil(p / 100 * len(ascending_values)) - 1]


if __name__ == "__main__":
    gmail_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/gmail")
    counts = profile(gmail_dir / "raw", gmail_dir / "profile.json")
    print(json.dumps(counts, indent=2))

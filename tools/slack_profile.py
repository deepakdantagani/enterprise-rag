"""SLACK-0: count what is in the Slack corpus, straight from the 58 zips.

Every later Slack story quotes a number (how many threads, how long, which channels).
This writes those numbers to one file, data/slack/profile.json, so each one can be
reproduced. It only counts: it changes no file and decides no rule. Line 1 of a thread
is usually its channel, but 94 files carry a one-off topic name there
(`kv-residency-sim-harness-sync`); the profile lists every such word with its count and
leaves the channel rule to SLACK-5.

Run: uv run python -m tools.slack_profile

    >>> is_channel_shaped("customer-success"), is_channel_shaped("1719998880")
    (True, False)
    >>> percentile([5, 6, 7], 50)
    6
"""
import json
import math
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

CHANNEL_SHAPE = re.compile(r"[a-z][a-z0-9-]*")
CHARS_PER_TOKEN = 4


def profile(archives_dir: Path, out_path: Path) -> dict:
    """Count files, bytes, token percentiles and line-1 words; write them as JSON."""
    sizes, tokens, line1 = [], [], Counter()
    for archive in sorted(Path(archives_dir).glob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not name.endswith(".txt"):
                    continue
                raw = z.read(name)
                text = raw.decode("utf-8")
                sizes.append(len(raw))
                tokens.append(len(text) // CHARS_PER_TOKEN)
                line1[text.split("\n", 1)[0].strip()] += 1
    tokens.sort()
    shaped = {w: n for w, n in line1.items() if is_channel_shaped(w)}
    result = {
        "files": len(sizes),
        "bytes": sum(sizes),
        "tokens": {f"p{p}": percentile(tokens, p) for p in (50, 90, 99)} | {"max": tokens[-1]},
        "line1_channel_shaped": dict(sorted(shaped.items(), key=lambda kv: (-kv[1], kv[0]))),
        "line1_other": len(sizes) - sum(shaped.values()),
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n")
    return result


def is_channel_shaped(word: str) -> bool:
    """Lowercase letters, digits and dashes, starting with a letter: how channels are named."""
    return CHANNEL_SHAPE.fullmatch(word) is not None


def percentile(sorted_values: list[int], p: int) -> int:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it."""
    return sorted_values[math.ceil(p / 100 * len(sorted_values)) - 1]


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/slack")
    print(json.dumps(profile(root / "archives", root / "profile.json"), indent=2)[:400])

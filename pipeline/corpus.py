"""PARSE-2c, PARSE-2d: the raw folder -> the clean folder, one job per function.

cleaning.py and manifest.py are pure (no disk). This module is the only place that
reads and writes files for the cleaning step:

    raw file --read--> clean_text() --save_text--> clean file
                          |
                          +--> manifest_row() --save_manifest--> _manifest.json

Example (real corpus file dsid_a99282d9...service-catalog...txt):

    before, line 3 of the raw file is one 8,600-char line with "\\n" as text:
        'Summary:\\n\\nThis playbook defines the canonical service catalog ...'
    after, the clean file has real lines (149 of them):
        'Summary:'
        ''
        'This playbook defines the canonical service catalog ...'
"""
import json
from pathlib import Path

from pipeline.cleaning import clean_text
from pipeline.manifest import manifest_row


def save_text(path: Path, text: str) -> None:
    """Write one text file, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_manifest(clean_dir: Path, rows: list[dict]) -> None:
    """Write the manifest rows as a JSON list to clean_dir/_manifest.json."""
    save_text(clean_dir / "_manifest.json", json.dumps(rows, indent=1))


def write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]:
    """Clean every *.txt in raw_dir into clean_dir, save the manifest, return its rows.

    Files go in name order so the manifest order is stable; the golden fingerprint
    test hashes the rows in that order.
    """
    rows = []
    for src in sorted(raw_dir.glob("*.txt")):
        raw = src.read_text(encoding="utf-8")
        result = clean_text(raw)
        save_text(clean_dir / src.name, result.text)
        rows.append(manifest_row(src.name, raw, result))
    save_manifest(clean_dir, rows)
    return rows

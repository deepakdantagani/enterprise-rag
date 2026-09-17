"""PARSE-2c, PARSE-2d, PARSE-8c: raw folder -> clean folder -> markdown folder.

cleaning.py, to_markdown.py and manifest.py are pure (no disk). This module is the
only place that reads and writes corpus files. Each step owns its folder and the
_manifest.json inside it, and never writes into the folder it reads from:

    raw file --read--> clean_text() --save_text--> clean file
                          |
                          +--> manifest_row() --save_manifest--> _manifest.json

    clean file --read--> to_markdown() --save_text--> markdown file (same name, .md)
                          |
                          +--> markdown_row() --save_manifest--> _manifest.json

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
from pipeline.manifest import manifest_row, markdown_row
from pipeline.to_markdown import heading_lines, to_markdown


def save_text(path: Path, text: str) -> None:
    """Write one text file, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_manifest(folder: Path, rows: list[dict]) -> None:
    """Write the manifest rows as a JSON list to folder/_manifest.json."""
    save_text(folder / "_manifest.json", json.dumps(rows, indent=1))


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


def write_markdown_corpus(clean_dir: Path, markdown_dir: Path) -> list[dict]:
    """Write to_markdown of every *.txt in clean_dir into markdown_dir, save its manifest,
    return the rows. The markdown folder is derived data: delete it and run this again."""
    rows = []
    for src in sorted(clean_dir.glob("*.txt")):
        clean = src.read_text(encoding="utf-8")
        markdown = to_markdown(clean)
        row = markdown_row(src.name, clean, markdown, headings=len(heading_lines(markdown)))
        save_text(markdown_dir / row["file"], markdown)
        rows.append(row)
    save_manifest(markdown_dir, rows)
    return rows

"""GMAIL-2: clean every raw Gmail thread once into data/gmail/clean/, with a manifest beside it.

The only module of the Gmail cleaning stage that touches disk. GMAIL-1a (clean_thread)
stays pure; this reads each raw file, cleans it, writes it under the same name, and
writes `_manifest.json`: one row per thread with the sha256 of the raw and clean text,
whether the thread was escaped, and line and byte counts. It never writes into raw/.

    raw/<name>.txt --read--> clean_thread() --write--> clean/<name>.txt
                                   |
                                   +--> manifest_row() --save_manifest--> clean/_manifest.json

Files are read as bytes, not text: 69 threads hold a real carriage return, and reading
them as text would change them before they are hashed. Reuses the Confluence manifest_row
unchanged. It does not import pipeline.corpus: that pulls in the Confluence Markdown parser
just for two small helpers.

Run: uv run python -m pipeline.gmail.corpus
"""
import json
import sys
from pathlib import Path

from pipeline.gmail.cleaning import clean_thread
from pipeline.manifest import manifest_row

MANIFEST_NAME = "_manifest.json"


def write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]:
    """Clean every *.txt in raw_dir into clean_dir, save the manifest, return its rows.

    Files go in name order so the manifest order is stable; the golden fingerprint
    test hashes the rows in that order."""
    clean_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in sorted(raw_dir.glob("*.txt")):
        raw = source.read_bytes().decode("utf-8")
        result = clean_thread(raw)
        (clean_dir / source.name).write_text(result.text, encoding="utf-8")
        rows.append(manifest_row(source.name, raw, result))
    save_manifest(clean_dir, rows)
    return rows


def save_manifest(clean_dir: Path, rows: list[dict]) -> None:
    """A JSON list with one row per line, so a diff of two runs shows the files that changed."""
    lines = ",\n".join(json.dumps(row) for row in rows)
    (clean_dir / MANIFEST_NAME).write_text(f"[\n{lines}\n]\n" if rows else "[]\n", encoding="utf-8")


if __name__ == "__main__":
    gmail_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/gmail")
    rows = write_clean_corpus(gmail_dir / "raw", gmail_dir / "clean")
    print(f"{len(rows)} threads in, {len(rows)} out, "
          f"{sum(row['was_escaped'] for row in rows)} escaped, "
          f"{sum(row['clean_bytes'] for row in rows)} clean bytes")

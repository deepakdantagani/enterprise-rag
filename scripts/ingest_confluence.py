import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sources = sorted((root / "data/confluence/raw").glob("*.txt"))
output = root / "data/confluence/records.jsonl"

# JSONL stores one complete document record on each line.
with output.open("w", encoding="utf-8") as destination:
    for source in sources:
        record = {
            "doc_id": source.name.split("__", 1)[0],
            "source_type": "confluence",
            "source_path": str(source.relative_to(root)),
            "raw_content": source.read_bytes().decode("utf-8"),
        }
        destination.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"Saved {len(sources)} records to {output}")

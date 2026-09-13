# /// script
# requires-python = ">=3.11"
# dependencies = ["llama-index-readers-docling==0.5.0", "docling==2.126.0", "llama-index-core==0.14.24"]
# ///
"""Inspect Docling's native structure for one document through LlamaIndex."""

import hashlib
import json
from pathlib import Path

from llama_index.readers.docling import DoclingReader

root = Path(__file__).resolve().parent.parent
source = next((root / "data/confluence/raw").glob(
    "dsid_6570f95dc6104e34a53c539932c56f7c__*.txt"
))
# The existing Markdown preview has identical bytes; no headings are added.
preview = root / "data/confluence/preview/typical.md"
if preview.read_bytes() != source.read_bytes():
    raise ValueError("Preview differs from the original document")

metadata = {
    "doc_id": source.name.split("__", 1)[0],
    "source_type": "confluence",
    "source_path": str(source.relative_to(root)),
    "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
}
reader = DoclingReader(export_type=DoclingReader.ExportType.JSON)
document = reader.load_data(str(preview), extra_info=metadata)[0]
document.id_ = metadata["doc_id"]
result = {**document.metadata, "parsed": json.loads(document.text)}

output = root / "data/confluence/parsed/typical.docling.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Saved one parsed document to {output}")

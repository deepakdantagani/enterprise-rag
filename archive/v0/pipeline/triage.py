"""Triage gate for new Confluence exports.

Usage: python -m pipeline.triage [raw_dir] [clean_dir]
Runs the preprocessor, buckets every file, and flags files that need a human look
before they reach the chunker. Writes <clean_dir>/_triage.json and prints a summary.
Exit code 1 if any file needs review (handy for CI).
"""
import json, re, sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent.parent
from pipeline import preprocess as pre
from pipeline.structure import bucket, label_flags

raw_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else pre.RAW_DIR
clean_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else pre.CLEAN_DIR

MIN_BYTES, MAX_BYTES = 300, 30_000
RE_HTML = re.compile(r"<(table|div|br|p|ul|li|span|img|a|h\d|ac:|ri:)[ >/]", re.I)
RE_WIKI = re.compile(r"^(h[1-6]\. |\|\||\{code|\{noformat|\{panel|\{toc)", re.M)


def flags_for(raw: str, clean: str) -> list[str]:
    f = []
    b = bucket(clean)
    n = len(clean.encode())
    if n < MIN_BYTES: f.append(f"tiny ({n} B)")
    if n > MAX_BYTES: f.append(f"large ({n // 1000} KB)")
    if b == "D_prose": f.append("no markup (bucket D)")
    if not pre.is_escaped(raw) and raw.count("\\n") >= 5: f.append("literal \\n but unescape guard did not fire")
    if pre.is_escaped(raw) and clean.count("\\n") >= 5: f.append("literal \\n left after unescape")
    if RE_WIKI.search(clean): f.append("confluence wiki markup remains")
    if RE_HTML.search(clean): f.append("raw html tags")
    if b in ("C_plain_labels", "D_prose") and n > 2000:
        L = clean.splitlines()
        if sum(label_flags(L)) <= 1: f.append("label rule found no section headings")
    try: raw.encode("utf-8")
    except UnicodeEncodeError: f.append("non-utf8")
    return f


manifest, counts = pre.run(raw_dir, clean_dir)
rows = []
for m in manifest:
    raw = (raw_dir / m["file"]).read_text(encoding="utf-8", errors="replace")
    clean = (clean_dir / m["file"]).read_text(encoding="utf-8")
    fl = flags_for(raw, clean)
    rows.append({"file": m["file"], "bucket": bucket(clean), "bytes": m["clean_bytes"], "flags": fl, "needs_review": bool(fl)})
(clean_dir / "_triage.json").write_text(json.dumps(rows, indent=1))

review = [r for r in rows if r["needs_review"]]
print(f"{len(rows)} files, {len(review)} need review")
print("buckets:", dict(Counter(r["bucket"] for r in rows)))
print("flags:", dict(Counter(f for r in review for f in r["flags"]).most_common()))
for r in review[:15]:
    print(f"  {r['file'][:60]:60s} {r['bucket']:15s} {'; '.join(r['flags'])}")
if len(review) > 15: print(f"  ... {len(review) - 15} more in {clean_dir / '_triage.json'}")
sys.exit(1 if review else 0)

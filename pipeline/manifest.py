r"""PARSE-2b: one manifest row per cleaned file.

The manifest (data/confluence/clean/_manifest.json) is the audit trail of the
cleaning step: for each file, a fingerprint of the raw bytes, a fingerprint of the
clean bytes, whether the file was JSON-escaped, and line/byte counts before and after.
The golden-fingerprint test reads `file` + `clean_sha256`; the triage gate reads the
flag and the counts.

This module is pure: it is handed the name, the raw text and the CleanResult, and
returns a dict. No file IO, no cleaning.

Example (real corpus file dsid_a99282d9...service-catalog...txt):

    >>> from pipeline.cleaning import CleanResult
    >>> row = manifest_row("page.txt", "a\nb", CleanResult(text="a\nb\n", was_escaped=False))
    >>> row["raw_lines"], row["clean_lines"], row["raw_bytes"], row["clean_bytes"]
    (2, 2, 3, 4)
"""
import hashlib

from pipeline.cleaning import CleanResult


def manifest_row(name: str, raw: str, result: CleanResult) -> dict:
    """Build the manifest entry for one file.

    raw_lines counts newlines + 1 because a raw export may not end with a newline.
    clean_lines counts newlines only, because clean text always ends with exactly one
    (PARSE-1 `normalize` guarantees it).
    """
    clean = result.text
    return {
        "file": name,
        "raw_sha256": sha256(raw),
        "clean_sha256": sha256(clean),
        "was_escaped": result.was_escaped,
        "raw_lines": raw.count("\n") + 1,
        "clean_lines": clean.count("\n"),
        "raw_bytes": len(raw.encode("utf-8")),
        "clean_bytes": len(clean.encode("utf-8")),
    }


def sha256(text: str) -> str:
    """Hex fingerprint of the text's UTF-8 bytes.

    >>> sha256("")[:12]
    'e3b0c44298fc'
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

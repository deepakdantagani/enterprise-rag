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


def markdown_row(clean_name: str, clean: str, markdown: str, headings: int) -> dict:
    """Build the markdown manifest entry for one file (PARSE-8c).

    clean_sha256 ties the row to the clean manifest. rewritten_lines is the number of
    lines to_markdown changed: heading lines plus emptied underlines. headings is how
    many headings the Markdown copy has, title included; a page written in `#` has many
    headings and one rewritten line, so the two numbers answer different questions.
    """
    clean_lines, markdown_lines = clean.split("\n"), markdown.split("\n")
    if len(clean_lines) != len(markdown_lines):
        raise ValueError(f"{clean_name}: {len(clean_lines)} clean lines, {len(markdown_lines)} markdown lines")
    return {
        "file": clean_name.removesuffix(".txt") + ".md",
        "clean_file": clean_name,
        "clean_sha256": sha256(clean),
        "md_sha256": sha256(markdown),
        "rewritten_lines": sum(a != b for a, b in zip(clean_lines, markdown_lines)),
        "headings": headings,
    }


def sha256(text: str) -> str:
    """Hex fingerprint of the text's UTF-8 bytes.

    >>> sha256("")[:12]
    'e3b0c44298fc'
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

"""PARSE-2a: file handling around the pure cleaning rules.

cleaning.py never touches disk. This module does, one file at a time:

    raw file  --read-->  clean_text()  --write-->  clean file

Example (real corpus file dsid_a99282d9...service-catalog...txt):

    before, line 3 of the raw file is one 8,600-char line with "\\n" as text:
        'Summary:\\n\\nThis playbook defines the canonical service catalog ...'
    after, the clean file has real lines:
        'Summary:'
        ''
        'This playbook defines the canonical service catalog ...'
"""
from pathlib import Path

from pipeline.cleaning import CleanResult, clean_text


def clean_one_file(src: Path, dst: Path) -> CleanResult:
    """Read one raw file, clean it, write one clean file, report what happened.

    The destination folder is created if it does not exist.
    """
    result = clean_text(src.read_text(encoding="utf-8"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(result.text, encoding="utf-8")
    return result

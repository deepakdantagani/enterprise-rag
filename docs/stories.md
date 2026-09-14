# Parsing stories

One story = one function = one PR (about 60 lines including its tests). Stories below
PARSE-2 are still module-level; each gets split into one-function sub-stories (a, b, c)
when we reach it, not before. Every sub-story carries an "Example with real data"
section: a before/after taken from the actual corpus, so the change is concrete. Each story is independent:
it can be built and merged without the others, because the existing modules keep
working until a later story switches the caller over. TDD on every story: write the
acceptance tests first (red), then the code (green), then the PR.

Heading icons: ✅ Done · ⬜ To do (mirror the Status line).

Template for every story, in this order: Status · As a · I want to · So that ·
Acceptance Criteria (Gherkin) · Example with real data · Non-functional Requirements ·
Dependencies (APIs data contracts · Service Bus · Database updates · UI).

Shared non-functional requirements (apply to every story):
- Deterministic: same input, same output, no network, no model calls.
- Behaviour-preserving: after the story, `uv run python -m unittest discover tests` is
  green and the clean-folder manifest sha256 values are unchanged.
- Readable: top-of-file story, one idea per function, input -> output doctests, early returns.
- No Service Bus, database, or UI in any story below (marked N/A).

Glossary (terms used across the stories; a story should make sense without chat history):
- **Raw file**: one Confluence page exported as `.txt`, exactly as received, under `data/confluence/raw/`. 5,189 files.
- **Clean file**: the same page after the cleaning rules, under `data/confluence/clean/`, same file name.
- **JSON-escaped**: the export wrote the page body as a JSON string, so a line break is the two characters `\n`
  and a quote is `\"`. 910 of the raw files are like this. "Unescape" turns them back into real characters.
- **sha256**: a 64-character hex fingerprint of some bytes. Same bytes, same fingerprint; one byte changed, a completely different one. Used to prove which raw bytes produced which clean bytes.
- **Manifest**: `data/confluence/clean/_manifest.json`, one row per file (see PARSE-2b for the row). It is the audit trail of the cleaning step and the input to the triage gate (PARSE-10).
- **Golden fingerprint**: `tests/golden/corpus_fingerprint.json`, one sha256 over every clean file's sha256 in manifest order. If a refactor changes any clean file by one byte, this test fails. It is how we know a story preserved behaviour.
- **Bucket**: which markup style a clean file uses (A `#` headings, B underlined headings, C plain labels, D prose). See PARSE-3.
- **Label rule**: our own rule that finds headings written as bare lines such as `Overview` with no `#`. See PARSE-4.
- **markdown-it**: the Markdown parser library (`markdown-it-py`) we use for headings, lists, tables and code fences.
- **LlamaIndex**: the RAG framework the pipeline must plug into; our chunks become its `TextNode`s. See PARSE-9.

---

## PARSE-1  Text cleaning rules as a pure module  ✅

**Status:** Done (merged eee9ef3)

**As a** pipeline developer
**I want to** call the three cleaning rules (unescape, fix_structure, normalize) from a module that touches no files
**So that** the rules can be unit-tested and reused without a folder on disk

**Acceptance Criteria (Gherkin)**
- Given a string whose body is JSON-escaped, When I call `clean_text(raw)`, Then I get real newlines back and a flag `was_escaped=True`
- Given a normal string, When I call `clean_text(raw)`, Then the text is unchanged except whitespace tidy-up and `was_escaped=False`
- Given the module `pipeline/cleaning.py`, When I read its imports, Then it imports nothing that reads or writes files

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `clean_text(raw: str) -> CleanResult(text: str, was_escaped: bool)`; existing `is_escaped`, `unescape`, `fix_structure`, `normalize` keep their signatures
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-2  Corpus writer  (split into one function per PR)

### PARSE-2a  clean_one_file  ✅

**Status:** Done (merged ef9e404)

**As a** pipeline developer
**I want to** `clean_one_file(src, dst)` to read one raw file, clean it, and write one clean file
**So that** the smallest unit of file handling is testable on a temp folder

**Acceptance Criteria (Gherkin)**
- Given a raw file, When I call `clean_one_file(src, dst)`, Then `dst` contains `clean_text(src text).text`
- Given an escaped raw file, Then the return value says `was_escaped=True`
- Given `dst`'s folder does not exist, Then it is created

**Example with real data**  (`dsid_a99282d9a6c5422e8b14168701df46f2__service-c...txt`)

Before, the raw file. Line 3 is one long line, 8,600 characters, with `\\n` as text:
```
'Service Catalog Contract and Integration Playbook\n\nSummary:\\n\\nThis playbook defines the canonical service catalog contract for model and variant metadata and d'...
```
After, the clean file. Real lines:
```
'Service Catalog Contract and Integration Playbook\n\nSummary:\n\nThis playbook defines the canonical service catalog contract for model and variant metadata and doc'...
```
Return value: `CleanResult(text=<the clean text>, was_escaped=True)`

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `clean_one_file(src: Path, dst: Path) -> CleanResult`  (uses PARSE-1 `clean_text`)
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-2b  manifest_row  ✅

**Status:** Done (merged 4937390)

**As a** pipeline developer
**I want to** `manifest_row(name, raw, result)` to build one manifest entry
**So that** the row shape is defined in exactly one place

**Background**
The manifest is a JSON list with one row per file, written next to the clean files as
`_manifest.json`. Two things read it: the golden-fingerprint test (uses `file` and
`clean_sha256`) and the triage gate in PARSE-10 (uses `was_escaped` and the line and byte
counts to spot files that look wrong). This story builds one row from three inputs it is
handed: the file name, the raw text, and the `CleanResult` from PARSE-1. It reads no files
and computes no cleaning, so it is a pure function like `clean_text`.

**Acceptance Criteria (Gherkin)**
- Given a name, raw text and a CleanResult, When I call it, Then I get a dict with keys `file, raw_sha256, clean_sha256, was_escaped, raw_lines, clean_lines, raw_bytes, clean_bytes`
- Given the same inputs twice, Then the two dicts are equal
- Given `raw="a\nb"` (no trailing newline) and clean text `"a\nb\n"`, Then `raw_lines=2`, `clean_lines=2`, `raw_bytes=3`, `clean_bytes=4`
- Given `pipeline/manifest.py`, When I read its imports, Then it imports nothing that reads or writes files (same rule as PARSE-1)

**Example with real data**  (same file)
```json
{
  "file": "dsid_a99282d9a6c5422e8b14168701df46f2__service-catalog-contract-integration-playbook-2026-12-01.txt",
  "raw_sha256": "f8d6d71ca99d591405998474f382e25b2301e709b49bf6ce4c86afa9010bfe12",
  "clean_sha256": "2ad5d14f3f643429548be9a5db2ad33cc9413005841af0b0f7c72aab0c797523",
  "was_escaped": true,
  "raw_lines": 3,
  "clean_lines": 149,
  "raw_bytes": 8555,
  "clean_bytes": 8401
}
```
`raw_lines` 3 -> `clean_lines` 149: that is the unescape doing its work. `was_escaped` true. The two sha256 values let you prove later which raw bytes produced which clean bytes.

**Key definitions**

| Key | Type | How it is computed | Why it is there |
|---|---|---|---|
| `file` | str | the raw file's name, e.g. `dsid_...txt` | joins the row to the raw and clean files (same name in both folders) |
| `raw_sha256` | str | `sha256(raw.encode("utf-8")).hexdigest()` | fingerprint of the input; changes only if the export changes |
| `clean_sha256` | str | `sha256(result.text.encode("utf-8")).hexdigest()` | fingerprint of the output; the golden check hashes these in order |
| `was_escaped` | bool | `result.was_escaped` from `clean_text` | tells you the file was JSON-escaped and got unescaped (910 of 5,189) |
| `raw_lines` | int | `raw.count("\n") + 1` | line count of the input (raw files may not end with a newline, so +1) |
| `clean_lines` | int | `result.text.count("\n")` | line count of the output (clean text always ends with exactly one newline, so no +1) |
| `raw_bytes` | int | `len(raw.encode("utf-8"))` | size of the input in bytes |
| `clean_bytes` | int | `len(result.text.encode("utf-8"))` | size of the output in bytes; a big drop means content was lost, worth a look |

In the example: `raw_lines` 3 vs `clean_lines` 149 shows the unescape; `raw_bytes` 8555 vs `clean_bytes` 8401 is only the two-character `\n` becoming one real newline, so nothing was lost.

Why `raw_lines` has `+ 1` and `clean_lines` does not: a raw export may or may not end
with a newline, so counting newlines under-counts by one for a file whose last line has
no newline; `+ 1` gives the number of lines for the common case. Clean text always ends
with exactly one newline (PARSE-1 `normalize` guarantees it), so the newline count is
exactly the line count. These are the formulas the reference implementation used, and the
golden fingerprint depends only on `clean_sha256`, so they stay as they are.

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `manifest_row(name: str, raw: str, result: CleanResult) -> dict` in `pipeline/manifest.py`; uses PARSE-1 `CleanResult`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-2c  write_clean_corpus  ✅

**Status:** Done (merged cddd3ab)

**As a** pipeline developer
**I want to** `write_clean_corpus(raw_dir, clean_dir)` to run 2a over every `.txt` and save the rows from 2b as `_manifest.json`
**So that** one command produces the clean folder

**Background**
This is the loop that turns the raw folder into the clean folder. It has no rules of its
own; it composes the two finished pieces:

1. list every `*.txt` in `raw_dir`, sorted by file name (the manifest order must be
   stable, because the golden fingerprint hashes the rows in order)
2. for each file: read the raw text, call PARSE-2a `clean_one_file(src, clean_dir / src.name)`,
   build the row with PARSE-2b `manifest_row(src.name, raw, result)`
3. write the rows as a JSON list to `clean_dir / "_manifest.json"`, and return the same list

The raw text is read here for the manifest row and again inside `clean_one_file`. Two
reads of a 10 KB file is cheaper than widening 2a's return type, so we accept it.

Golden check, in words: take each row's `file` and `clean_sha256`, join them with one
space, one row per line, sha256 the whole thing. The result must equal the
`fingerprint_sha256` in `tests/golden/corpus_fingerprint.json`
(`22453b4e…62920`, 5,189 files, 910 escaped). That value came from the archived v0
code; matching it proves 2a + 2b + 2c reproduce v0 byte for byte on every file.

**Acceptance Criteria (Gherkin)**
- Given a folder with two raw files, When I run it, Then two clean files and `_manifest.json` with two rows exist
- Given an empty folder, Then an empty manifest and no error
- Given `raw_dir` with `b.txt` and `a.txt`, Then the manifest rows are in the order `a.txt`, `b.txt`
- Given the real raw folder `data/confluence/raw/` exists, When I run it into a temp folder, Then the fingerprint of the returned rows equals `tests/golden/corpus_fingerprint.json`; if the raw folder is missing (fresh clone, data is gitignored), the test is skipped, not failed

**Example with real data**  (`data/confluence/clean/_manifest.json`, first two of 5,189 rows)
```json
[
 {"file": "dsid_000aabb424694648b5651aa9a2438c81__operational-onboarding-and-authorization-playbook-2028.txt",
  "raw_sha256": "...", "clean_sha256": "...", "was_escaped": false,
  "raw_lines": 194, "clean_lines": 193, "raw_bytes": 9749, "clean_bytes": 9748},
 {"file": "dsid_000dce03310548ffa90f5d2f706a92df__customer-security-questionnaire-exception-...txt",
  "raw_sha256": "...", "clean_sha256": "...", "was_escaped": false,
  "raw_lines": 120, "clean_lines": 120, "raw_bytes": 6402, "clean_bytes": 6403}
]
```
`_manifest.json` is written with `json.dump(rows, f, indent=1)`; formatting does not affect the golden check, which uses only the values.

Golden check: hash the lines `<file> <clean_sha256>` in order; it must equal `tests/golden/corpus_fingerprint.json`:
```python
lines = "\n".join(f"{r['file']} {r['clean_sha256']}" for r in rows)
sha256(lines.encode("utf-8")).hexdigest() == golden["fingerprint_sha256"]
```

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]` in `pipeline/corpus.py` next to 2a; uses 2a `clean_one_file`, 2b `manifest_row`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-2d  Fix: one job per function in corpus.py (SOLID)  ✅

**Status:** Done (merged cddd3ab)

**As a** code reviewer
**I want to** every function in `pipeline/corpus.py` to do exactly one thing that its name says
**So that** reading, cleaning, saving and the loop can each be understood and tested alone

**Background**
Review of PARSE-2a and 2c found two Single Responsibility breaks:
- `clean_one_file(src, dst)` reads, cleans and writes. Its name says "clean" only. Cleaning
  already lives in PARSE-1 `clean_text`, so this function hides a save behind a clean name.
- `write_clean_corpus` builds the JSON and writes `_manifest.json` inline, a second job
  inside the loop function.
A side effect of the first break: the loop read each raw file twice (once for the
manifest row, once inside `clean_one_file`).

The fix: delete `clean_one_file`; add two save functions with one job each; the loop
calls the pure functions and the save functions in order. Nothing else changes.

Before (2a + 2c as merged/proposed):
```
write_clean_corpus
  for each src:
    raw = read(src)
    result = clean_one_file(src, dst)        # read again + clean + write
    row = manifest_row(name, raw, result)
  write _manifest.json inline               # json.dumps + write_text
```
After:
```
write_clean_corpus
  for each src:
    raw = read(src)                         # read once
    result = clean_text(raw)                # PARSE-1, pure
    save_text(clean_dir / name, result.text)  # one job: write one file
    row = manifest_row(name, raw, result)   # PARSE-2b, pure
  save_manifest(clean_dir, rows)            # one job: rows -> _manifest.json
```

**Acceptance Criteria (Gherkin)**
- Given a path whose folder does not exist, When I call `save_text(path, "x\n")`, Then the folder is created and the file contains exactly `"x\n"`
- Given two rows, When I call `save_manifest(clean_dir, rows)`, Then `clean_dir/_manifest.json` parses back to the same two rows
- Given `pipeline/corpus.py`, When I grep it, Then `clean_one_file` is gone and `write_clean_corpus` contains no `json.` call
- Given the existing 2c tests (two files, empty folder, name order, golden fingerprint), Then they pass unchanged
- Given the real raw folder, Then each raw file is read exactly once per run

**Example with real data**  (same file as 2a)
Nothing about the data changes. `dsid_a99282d9…` still becomes 149 clean lines with
`was_escaped=true`, and the golden fingerprint stays `22453b4e…62920`. This story moves
code, it does not change output; the golden test is what proves that.

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).
- One function = one verb in its name = one job in its body.

**Dependencies**
- APIs: `save_text(path: Path, text: str) -> None`; `save_manifest(clean_dir: Path, rows: list[dict]) -> None`; `write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]` (signature unchanged). `clean_one_file` removed; `tests/test_corpus.py` replaced by tests for `save_text`.
- Uses: PARSE-1 `clean_text`, PARSE-2b `manifest_row`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-3  Bucket classifier  ✅

**Status:** Done (merged f1937e3)

**As a** pipeline developer
**I want to** ask one function which markup style a clean file uses
**So that** the chunker can pick the right heading detector

**Background**
The clean files are not written one way. Some authors used Markdown `#` headings, some
underlined their headings with `-----`, most wrote bare labels like `Overview:` with no
markup at all, and a few wrote plain prose. Each style needs a different heading
detector (PARSE-5, PARSE-6), so we first need one small, deterministic function that
says which style a file is: its **bucket**.

The rule is "strongest signal wins", checked in this order, first match returns:

| Bucket | Test (regex, multiline) | Files | Meaning |
|---|---|---|---|
| `A_hash` | `^#{1,6} ` anywhere | 1,645 (31.7%) | at least one `# Heading` line |
| `B_setext` | `^[^\n]{1,80}\n(=+\|-{3,})\s*$` | 781 (15.1%) | a short line over `=====` or `-----` |
| `C_plain_labels` | `^\s*([-*+]\|\d+[.)]) \|^\|\|^```` | 2,751 (53.0%) | no headings, but lists, tables or code fences |
| `D_prose` | none of the above | 12 (0.2%) | paragraphs only, or empty |

Order matters: a file with one `#` heading and ten underlined ones is `A_hash`, because
`#` is the more reliable signal and markdown-it handles both anyway.

**Acceptance Criteria (Gherkin)**
- Given `"# Title\n\ntext"`, When I call `bucket(text)`, Then I get `"A_hash"`
- Given `"Title\n-----\n\ntext"`, Then `"B_setext"`
- Given `"Overview\n\n- item"`, Then `"C_plain_labels"`
- Given `"Just prose.\n\nMore prose."` or `""`, Then `"D_prose"`
- Given `"Intro\n-----\n\n# Real\n\n- item"` (both signals), Then `"A_hash"`
- Given `pipeline/buckets.py`, When I read it, Then it holds `bucket`, its three regexes and nothing else, and no file IO
- Given every file in `data/confluence/clean/`, When I bucket them all, Then the counts are exactly A 1,645 · B 781 · C 2,751 · D 12 (the v0 result in `_buckets.json`); skipped if the data folder is missing

**Example with real data**  (first 200 characters of one clean file per bucket)

`A_hash` · `dsid_000dce03…customer-security-questionnaire…txt`
```
Customer Security Questionnaire Exceptions Policy

## Purpose
This policy defines how Redwood Inference responds when a customer security questionnaire ...
```
`B_setext` · `dsid_00111a3c…fallback-validation…txt`
```
Fallback validation and chaos test plan for graceful runtime fallbacks

Purpose
-------
This document defines a repeatable validation and chaos-testing plan ...
```
`C_plain_labels` · `dsid_0012a01f…scheduler-health-oracle…txt`
```
Scheduler Health Oracle and Self‑Heal Procedures

Overview:

This playbook defines the Scheduler Health Oracle (SHO) — an auditable, real‑time decision layer ...
```
`D_prose` · `dsid_5e65a1cb…sev2-dedicated-autoscaler…txt`
```
Postmortem: SEV-2 Dedicated autoscaler stuck at min capacity (2026-02-09)

The Dedicated autoscaler stopped scaling above min due to a metrics query change ...
Two Dedicat...
```
Input is the whole clean text as one string; output is one of the four strings.
`bucket(<A text>) == "A_hash"`, and so on for the other three.

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).
- Pure: no file IO in `buckets.py` (same rule as PARSE-1 and 2b).

**Dependencies**
- APIs: `bucket(text: str) -> str`, one of `"A_hash" | "B_setext" | "C_plain_labels" | "D_prose"`, in `pipeline/buckets.py`
- Uses: nothing from earlier stories (reads the clean text it is handed)
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-4  Label rule as its own module  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** the plain-label heading rule in `pipeline/label_rule.py` with only the rule and its helpers
**So that** the rule can be read, tested, and tuned without the debug and measurement code around it

**Acceptance Criteria (Gherkin)**
- Given the current `label_flags` tests, When I point them at `pipeline.label_rule`, Then they pass unchanged
- Given `pipeline/label_rule.py`, When I read it, Then it has no `explain`, no recall check, no corpus loop, no `__main__`
- Given a line with no blank line above and a non-label above, When I call `label_flags`, Then that line is not a heading

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `label_flags(lines: list[str]) -> list[bool]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-5  Heading detector interface + Markdown implementation  ⬜

**Status:** To do

**As a** chunker developer
**I want to** call one `find_headings(lines)` method and get headings regardless of how they were written
**So that** the chunker never knows about `#`, underlines, or the label rule

**Acceptance Criteria (Gherkin)**
- Given lines with `## Scope` at index 4, When I call `MarkdownHeadings().find_headings(lines)`, Then I get `[Heading(line=4, level=2, text="Scope")]`
- Given `Scope` over `-----` at index 4, Then `[Heading(line=4, level=2, text="Scope")]` and the underline line is not a heading
- Given a `#` inside a fenced code block, Then it is not reported
- Given any detector, When I call it on `[]`, Then I get `[]`

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `Heading(line: int, level: int, text: str)`; `HeadingDetector` protocol with `find_headings(lines: list[str]) -> list[Heading]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-6  Label heading detector + selector  ⬜

**Status:** To do

**As a** chunker developer
**I want to** a second detector that wraps the label rule, and one function that picks the detector for a file
**So that** adding a third way to find headings never touches the chunker

**Acceptance Criteria (Gherkin)**
- Given lines `["Title", "", "Overview", "", "Body."]`, When I call `LabelHeadings().find_headings(lines)`, Then I get `[Heading(0,1,"Title"), Heading(2,2,"Overview")]`
- Given a bucket-A text, When I call `detector_for(text)`, Then I get a `MarkdownHeadings`
- Given a bucket-C text, Then a `LabelHeadings`
- Given both detectors, When I run them on the same lines, Then both return `list[Heading]` sorted by line

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `LabelHeadings`, `detector_for(text) -> HeadingDetector`
- Uses: PARSE-3, PARSE-4, PARSE-5
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-7  Blocks from markdown-it  ⬜

**Status:** To do

**As a** chunker developer
**I want to** the file as a list of top-level blocks with line ranges and a kind (text / list / table / code / quote)
**So that** the chunker can keep whole blocks together without knowing markdown-it tokens

**Acceptance Criteria (Gherkin)**
- Given a fenced code block on lines 10-14, When I call `blocks(text)`, Then one block has `kind="code", start=10, end=15`
- Given a bullet list on lines 3-6, Then one block with `kind="list"` covering exactly those lines
- Given a pipe table, Then one block `kind="table"`
- Given two paragraphs separated by a blank line, Then two `kind="text"` blocks
- Given the blocks for any fixture file, When I take the union of their line ranges, Then every non-blank line is covered exactly once

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `Block(kind: str, start: int, end: int)`; `blocks(text: str) -> list[Block]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-8  Chunker  ⬜

**Status:** To do

**As a** RAG developer
**I want to** turn blocks + headings into section-aware chunks, with no LlamaIndex in the module
**So that** the chunking logic is testable on plain strings

**Acceptance Criteria (Gherkin)**
- Given headings at lines 2 and 8 and blocks in between, When I call `chunk(lines, blocks, headings, max_chars)`, Then no chunk spans a heading
- Given a list block larger than `max_chars`, Then it is emitted as one chunk on its own, never split
- Given blocks that together fit in `max_chars`, Then they are packed into one chunk
- Given a heading followed directly by another heading, Then the second one's path includes the first
- Given every fixture file, Then every non-blank non-heading line is in exactly one chunk

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `Chunk(start: int, end: int, heading_path: list[str], block_kinds: list[str])`; `chunk(...) -> list[Chunk]`
- Uses: PARSE-5, PARSE-7
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-9  LlamaIndex adapter  ⬜

**Status:** To do

**As a** RAG developer
**I want to** a `NodeParser` that wraps the chunker and produces `TextNode`s
**So that** the pipeline plugs into LlamaIndex without the chunker depending on it

**Acceptance Criteria (Gherkin)**
- Given a `Document`, When I call `ConfluenceNodeParser().get_nodes_from_documents([doc])`, Then each node's text starts with `"<title> > <section>\n\n"` and metadata has `line_start`, `line_end`, `heading_path`
- Given `nodes.py`, When I read it, Then it contains no chunking rules, only the mapping `Chunk -> TextNode`
- Given the current `test_nodes.py`, Then it passes unchanged

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- APIs: `ConfluenceNodeParser(max_chars=1600)`
- Uses: PARSE-6, PARSE-7, PARSE-8
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-10  Triage gate on the new modules  ⬜

**Status:** To do

**As a** data owner
**I want to** the triage gate to use the new modules and keep its current flags
**So that** new exports are checked the same way after the refactor

**Acceptance Criteria (Gherkin)**
- Given the raw corpus, When I run `python -m pipeline.triage`, Then `_triage.json` lists the same 117 files with the same flags as before the refactor
- Given a folder with one escaped and one normal file, When I run triage on it, Then it exits 0 and flags nothing

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- Uses: PARSE-2, PARSE-3, PARSE-4
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-11  Debug and measurement tools out of the pipeline  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** `explain` and the recall self-check under `tools/`, not `pipeline/`
**So that** `pipeline/` contains only code that data flows through

**Acceptance Criteria (Gherkin)**
- Given `tools/explain.py <file>`, When I run it, Then I get the per-line HEADING / reason table
- Given `tools/measure.py`, When I run it, Then I get the bucket counts and the recall number
- Given `pipeline/`, When I grep for `explain` or `recall_against`, Then there are no matches

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).

**Dependencies**
- Uses: PARSE-3, PARSE-4
- Service Bus: N/A · Database: N/A · UI: N/A

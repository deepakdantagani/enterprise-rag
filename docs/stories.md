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

## PARSE-4  Label rule as its own module  (split into one function per PR)

**Background for all of PARSE-4**
53% of the clean files (bucket C) have headings with no markup at all: a short bare line
such as `Overview:` or `High-level design`, usually with a blank line above it. Markdown
parsers see plain paragraphs there. The **label rule** is our own rule that flags those
lines as headings. It has two halves:

1. **Shape**: does this one line, on its own, look like a label? (short, no block marker,
   no closing punctuation, not a sentence, not a `key: long value` field, has a real word)
2. **Neighbours**: is it in a place where a label can be? (line 1 is always the title;
   not inside a code fence; not indented; blank line above, or the line above is itself a
   label; a numbered line only if blank above and below)

Real example, `dsid_0012a01f…scheduler-health-oracle…txt` (bucket C, 143 lines, 20 labels).
First 24 lines, `HEADING` where the rule fires:
```
  0 HEADING 'Scheduler Health Oracle and Self‑Heal Procedures'      <- line 1 is the title
  1         ''
  2 HEADING 'Overview:'                                             <- short, blank above
  3         ''
  4         'This playbook defines the Scheduler Health Oracle (SHO) — ...'   <- sentence
  5         ''
  6 HEADING 'Audience:'
  7         '- Oncall SREs and runtime engineers'                    <- list item
  8         '- Kernel and scheduler owners'
  9         '- Runtime observability and automation engineers'
 10         ''
 11 HEADING 'Why SHO: problem statement'                            <- key: short value, ok
 12         '- Scheduler-level regressions (priority inversion, ...'
 13         '- Manual triage is slow; highly-automated remediation ...'
 14         '- The SHO provides a standard decision contract and ...'
 15         ''
 16 HEADING 'High-level design'
 17         '1) Signal ingestion: aggregated telemetry from ...'      <- numbered, tight list
 18         '2) Feature synthesis: rolling-error rates, ...'
 ...
 23 HEADING 'Detection signals and thresholds (baseline)'
```
Golden check for the whole rule: `tests/golden/label_fingerprint.json`, a sha256 over
`<file> <label count>` for all 5,189 clean files (104,537 labels in total), computed
from the archived v0 code. Matching it proves the rewrite flags exactly the same lines.

Module: `pipeline/label_rule.py`. Pure (no file IO). Public names have no underscore;
every function has input -> output doctests.

### PARSE-4a  Reject helpers: looks_like_a_sentence, is_key_with_long_value  ✅

**Status:** Done (merged 087dcda)

**As a** pipeline developer
**I want to** two small predicates that say "this line is prose" and "this line is a field"
**So that** the shape test in 4b can reject them with one call each

**Acceptance Criteria (Gherkin)**
- Given `"The service restarts on failure"`, When I call `looks_like_a_sentence`, Then `True` (starts with a sentence word: We, This, The, It, If, You, Use, All)
- Given `"Manual triage is slow, remediation must be conservative, safe, and audited"` (comma and more than 8 words), Then `True`
- Given `"Testing, canaries and chaos simulation:"` (comma but short), Then `False`
- Given `"Owner: Identity and Access team second approver required"`, When I call `is_key_with_long_value`, Then `True`
- Given `"Owner: one two three four five"` (5-word value), Then `False`; given a 6-word value, Then `True` (the threshold is 6 or more words)
- Given `"Goals:"` (trailing colon), `"Appendix: Example Mappings"` (short value), `"Stage 4: Expand to Dedicated deployments today"` (label-like key), `"Q: Can we extend a lease mid-window?"`, Then `False` for each
- Given `"Why SHO: problem statement"` (from the real example), Then `False`

**Example with real data**  (lines from the file above)
| line | looks_like_a_sentence | is_key_with_long_value |
|---|---|---|
| `This playbook defines the Scheduler Health Oracle (SHO) — an auditable...` | True | False |
| `Why SHO: problem statement` | False | False |
| `Overview:` | False | False |

**Non-functional Requirements**
- Shared NFRs at the top of this file. Pure module.

**Dependencies**
- APIs: `looks_like_a_sentence(line: str) -> bool`; `is_key_with_long_value(line: str) -> bool`; regexes `SENTENCE_STARTER`, `KEY_COLON_VALUE`, `LABEL_LIKE_KEY`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-4b  is_label_shaped  ✅

**Status:** Done (merged 92bd790)

**As a** pipeline developer
**I want to** one predicate that says whether a single stripped line has the shape of a label
**So that** the shape half of the rule is testable with no neighbours involved

**Acceptance Criteria (Gherkin)**
- Given `"Rollout & Risk Controls"`, `"Phase 1: Data-source plumbing (Week 1-3)"`, `"Testing, canaries and chaos simulation:"`, When I call `is_label_shaped`, Then `True`
- Given a line over 80 characters, or over 12 words, Then `False`
- Given a line starting with a block marker (`|`, `>`, three backticks, `#`, `---`, `***`, `___`, `{`, `}`, `[`, `]`), Then `False`
- Given a line ending in `.`, `;` or `,`, Then `False`
- Given a line where `looks_like_a_sentence` or `is_key_with_long_value` is True (4a), Then `False`
- Given a line with no two letters in a row (e.g. `--kvcache-async`, `123`), or starting with `-` or `/`, Then `False`
- Given `""`, Then `False`

**Example with real data**  (first non-blank lines of the file above, shape only)
```
'Scheduler Health Oracle and Self‑Heal Procedures'   True
'Overview:'                                          True
'This playbook defines the Scheduler Health ...'     False   (sentence)
'Audience:'                                          True
'- Oncall SREs and runtime engineers'                False   (starts with -)
'Why SHO: problem statement'                         True
'High-level design'                                  True
```
Note: shape alone says `Audience:` and `Overview:` are labels; whether they are headings
also depends on the neighbours (4d). Shape is necessary, not sufficient.

**Non-functional Requirements**
- Shared NFRs. Pure. One early return per reject reason, in the order listed above.

**Dependencies**
- APIs: `is_label_shaped(line: str) -> bool`; constants `MAX_LABEL_CHARS = 80`, `MAX_LABEL_WORDS = 12`; regexes `BLOCK_MARKER`, `HAS_A_WORD`
- Uses: PARSE-4a
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-4c  is_numbered_heading  ✅

**Status:** Done (merged 368138a)

**As a** pipeline developer
**I want to** a predicate that tells a numbered heading (`3) Escalation`, alone) from a numbered list item (`1) first` / `2) second`, tight)
**So that** numbered section titles become headings and numbered lists stay lists

**Acceptance Criteria (Gherkin)**
- Given lines `["T", "", "3) Escalation", "", "Body."]` and index 2, When I call `is_numbered_heading(lines, 2)`, Then `True` (blank above and below)
- Given `["T", "", "1) first", "2) second"]` and index 2, Then `False` (line below is not blank)
- Given `["T", "", "- bullet", "", "Body."]` and index 2, Then `False` (only digits count)
- Given the numbered line is the last line, Then "below" counts as blank
- Given `"10.1 Sub-section"` style numbers, Then they count as numbered

**Example with real data**  (file above)
```
 16 HEADING 'High-level design'
 17         '1) Signal ingestion: ...'    <- index 17: above is a heading not blank, below is '2) ...' -> False, stays a list
```
and from `dsid_a99282d9…service-catalog…txt` a lone `3) Escalation` with blank lines
around it -> True, it is a section heading.

**Non-functional Requirements**
- Shared NFRs. Pure.

**Dependencies**
- APIs: `is_numbered_heading(lines: list[str], i: int) -> bool`; regex `NUMBERED_LINE`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-4d  label_flags  ✅

**Status:** Done (merged 4f27c77)

**As a** pipeline developer
**I want to** `label_flags(lines)` to return one True/False per line, using 4b for shape and the neighbour rules for position
**So that** the heading detector for bucket C (PARSE-6) is a single call

**Acceptance Criteria (Gherkin)**
- Given `["Title", "", "Overview", "", "Body text.", "", "Goals:", "- a"]`, When I call `label_flags`, Then `[True, False, True, False, False, False, True, False]`
- Given `["Title", "", "Parent", "Child label", "", "Body."]` (stacked labels), Then `[True, False, True, True, False, False]`
- Given `["Title", "", "Body text.", "Not a label"]` (no blank above), Then `[True, False, False, False]`
- Given lines inside a code fence, Then all `False`, and the fence lines themselves are `False`
- Given an indented label-shaped line, Then `False`
- Given a list item or numbered line, Then the flag is `is_numbered_heading(lines, i)` (4c)
- Given `[]`, Then `[]`; given a first line that is empty or opens a fence, Then line 1 is not the title
- Given every clean file, When I count True flags per file and fingerprint them, Then it equals `tests/golden/label_fingerprint.json` (5,189 files, 104,537 labels); skipped if the data folder is missing

**Example with real data**
The 24-line listing in the PARSE-4 background is exactly `label_flags` on that file:
20 headings out of 143 lines.

**Walkthrough with the two core rules only** (line 0 is the title; any other line is a
heading if it is label-shaped and the line above is blank):
```
i  line                  label-shaped?   above blank?   flags[i]
0  Title                 (title rule)    -              True
1  (blank)               no              -              False
2  Overview              yes             yes            True
3  (blank)               no              -              False
4  This is body text.    no (sentence)   -              False
```
Result `[True, False, True, False, False]`. The fence, indent, numbered and stacked
checks are extra ways to say no or yes on top of these two rules.

**Non-functional Requirements**
- Shared NFRs. Pure. Output length always equals input length.

**Dependencies**
- APIs: `label_flags(lines: list[str]) -> list[bool]`; helpers `is_title_line`, `is_fence_marker`, `is_indented`; regex `LIST_ITEM`
- Uses: PARSE-4b, PARSE-4c
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-5  Heading detector interface + Markdown implementation  (split into one function per PR)

**Background for all of PARSE-5**
The chunker (PARSE-8) needs to know where the headings are, but it must not care *how*
they were written. Files in bucket A/B write headings in Markdown (`## Scope`, or
`Scope` over `-----`); files in bucket C write bare labels that only our label rule
(PARSE-4) can see. So we define one small interface and two implementations:

```
HeadingDetector.find_headings(lines) -> list[Heading]      the contract
    MarkdownHeadings     uses markdown-it                   this story (5b)
    LabelHeadings        uses label_flags                   PARSE-6
```
A `Heading` is three values: `line` (0-based index into `lines`), `level` (1 for the
title, 2+ for sections), `text` (the heading text, stripped of `#` and whitespace).

How markdown-it reports a heading: `MarkdownIt("commonmark").enable("table").parse(text)`
returns a flat token list. A heading is a `heading_open` token whose `tag` is `h1`..`h6`
and whose `map` is `[start_line, end_line)`; the text is in the next token's `content`.
Only tokens at nesting `level == 0` are top-level (a `#` inside a blockquote or list is
nested and skipped); a `#` inside a code fence is never a token at all. For a setext
heading (`Scope` over `-----`) the map covers two lines; we report `line = map[0]`, the
text line, and the underline is not a heading.

Title rule, shared by every detector: line 0, when non-blank, is the document title,
level 1, even if it has no markup. If markdown-it already reported a heading at line 0,
we keep that one and do not add a second.

Real example, bucket A `dsid_000dce03…customer-security-questionnaire…txt` (297 lines, 41 headings):
```
lines[0..3]:  'Customer Security Questionnaire Exceptions Policy', '', '## Purpose', 'This policy defines ...'
find_headings -> [Heading(line=0, level=1, text='Customer Security Questionnaire Exceptions Policy'),   <- title rule
                  Heading(line=2, level=2, text='Purpose'),
                  Heading(line=11, level=2, text='Scope'),
                  Heading(line=21, level=2, text='Definitions'), ...]
```
Bucket B `dsid_00111a3c…fallback-validation…txt` (145 lines, 16 headings):
```
lines[0..3]:  'Fallback validation and chaos test plan ...', '', 'Purpose', '-------'
find_headings -> [Heading(line=0, level=1, text='Fallback validation and chaos test plan ...'),
                  Heading(line=2, level=2, text='Purpose'),      <- line 3 '-------' is not reported
                  Heading(line=6, level=2, text='Scope'), ...]
```
Golden check: `tests/golden/markdown_headings_fingerprint.json`, a sha256 over
`<file> <heading count>` for all 5,189 clean files (44,996 headings; A 31,622 · B 10,502
· C 2,860 · D 12). Computed once with the v0 logic. Bucket C/D files get only their title
line plus any stray Markdown; the label rule fills the rest in PARSE-6.

Module: `pipeline/headings.py`. Pure (no file IO).

### PARSE-5a  Heading value and HeadingDetector interface  ✅

**Status:** Done (merged ebb2d0f)

**As a** chunker developer
**I want to** a `Heading` value type and a `HeadingDetector` protocol
**So that** the chunker and both detectors agree on one data shape before any detector exists

**Acceptance Criteria (Gherkin)**
- Given `Heading(line=2, level=2, text="Scope")`, When I read its fields, Then I get `2`, `2`, `"Scope"`, and it is frozen (assigning raises) and comparable by value
- Given `HeadingDetector`, When I define a class with `find_headings(self, lines: list[str]) -> list[Heading]`, Then it satisfies the protocol without inheriting from it
- Given `pipeline/headings.py`, When I read it, Then it holds only `Heading`, `HeadingDetector` and nothing else yet

**Example with real data**
`Heading(line=2, level=2, text="Purpose")` is the second heading of the bucket A file above.

**Non-functional Requirements**
- Shared NFRs. Pure. `Heading` is a frozen dataclass; `HeadingDetector` is a `typing.Protocol`.

**Dependencies**
- APIs: `Heading(line: int, level: int, text: str)`; `HeadingDetector` with `find_headings(lines: list[str]) -> list[Heading]`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-5b  MarkdownHeadings  ✅

**Status:** Done (merged 9f367b0)

**As a** chunker developer
**I want to** `MarkdownHeadings().find_headings(lines)` to return the Markdown headings plus the title line
**So that** bucket A and B files get their structure from the parser, not from our rule

**Acceptance Criteria (Gherkin)**
- Given `["Title", "", "## Scope", "text"]`, When I call `find_headings`, Then `[Heading(0, 1, "Title"), Heading(2, 2, "Scope")]`
- Given `["Title", "", "Scope", "-----", "text"]` (setext), Then `[Heading(0, 1, "Title"), Heading(2, 2, "Scope")]` and line 3 is not reported
- Given `["# Title", "", "text"]`, Then `[Heading(0, 1, "Title")]` only once, not a duplicate from the title rule
- Given `["Title", "", "```", "# not a heading", "```"]`, Then `[Heading(0, 1, "Title")]`
- Given `["Title", "", "> # quoted"]` (nested), Then `[Heading(0, 1, "Title")]`
- Given `[]` or `[""]`, Then `[]`
- Given the result for any input, Then it is sorted by `line`
- Given every clean file, When I count headings per file and fingerprint them, Then it equals `tests/golden/markdown_headings_fingerprint.json`; skipped if the data folder is missing

**Example with real data**
The two listings in the PARSE-5 background are `MarkdownHeadings().find_headings(lines)` on those files: 41 and 16 headings.

Why the title rule is needed: markdown-it only finds headings with markup, and the
export writes the page title as a plain first line in every file.

| Line 0 in the 5,189 clean files | Files |
|---|---|
| Markdown heading (`# Title` or underlined) | 0 |
| Plain text | 5,189 |
| Blank | 0 |

So without `with_title`, every breadcrumb would lose the page name. Line 0 is always the
level-1 title unless it is blank; the "already reported" branch only guards a future
export that writes `# Title`.

**Non-functional Requirements**
- Shared NFRs. Pure. markdown-it is created once at module level (`MarkdownIt("commonmark").enable("table")`).

**Dependencies**
- APIs: `MarkdownHeadings` implementing `HeadingDetector`
- Uses: PARSE-5a; library `markdown-it-py`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-6  Label heading detector + selector  (split into one function per PR)

**Background for all of PARSE-6**
PARSE-5 gave us the interface (`find_headings(lines) -> list[Heading]`) and the Markdown
implementation. Bucket C files (53% of the corpus) have no Markdown headings, so they
need the second implementation: one that wraps the label rule from PARSE-4. Then one
tiny function decides, per file, which detector to use, so the chunker never looks at
buckets itself.

```
detector_for(text)
    bucket A_hash, B_setext     -> MarkdownHeadings()     markdown-it finds the headings
    bucket C_plain_labels, D    -> LabelHeadings()        label_flags finds the headings
```
`LabelHeadings` is a straight translation: every line where `label_flags` says True
becomes a `Heading`. Line 0 is level 1 (the title rule inside `label_flags`), every
other label is level 2; the label rule has no notion of depth.

Real example, bucket C `dsid_0012a01f…scheduler-health-oracle…txt` (143 lines, 20 labels):
```
label_flags(lines)  -> [True, False, True, False, False, False, True, ...]
LabelHeadings().find_headings(lines)
  -> [Heading(line=0,  level=1, text='Scheduler Health Oracle and Self‑Heal Procedures'),
      Heading(line=2,  level=2, text='Overview:'),
      Heading(line=6,  level=2, text='Audience:'),
      Heading(line=11, level=2, text='Why SHO: problem statement'),
      Heading(line=16, level=2, text='High-level design'), ...]      20 in total
detector_for("\n".join(lines))  -> LabelHeadings()      because bucket(text) == "C_plain_labels"
```
Golden check: `LabelHeadings` produces exactly one `Heading` per True flag, so its
per-file counts must equal `tests/golden/label_fingerprint.json` (104,537 headings).

**Known limit (checked 2026-09-14): bucket C files do have hierarchy, the label rule flattens it.**
Example `dsid_021076ec…sdk-patch-release-playbook…txt`: `Step-by-step playbook: detailed
procedure` (L28) is a parent and `Phase A … Phase D` (L30–L56) are its children, but all are
reported as level 2. Depth signals present in C+D label headings: numbered/Step/Phase/Stage
prefix 3,741 headings in 2,281 files; a label stacked directly under a label (`FAQ` then
`Q: …`) 1,513 in 748 files; dotted numbers 16 in 2 files. Chunk boundaries are unaffected;
only the middle of the breadcrumb is lost. Tracked as PARSE-12.

Module: `pipeline/headings.py` (same file as PARSE-5). Pure.

### PARSE-6a  LabelHeadings  ✅

**Status:** Done (merged 00b61e9)

**As a** chunker developer
**I want to** `LabelHeadings().find_headings(lines)` to turn the label rule's flags into `Heading` values
**So that** bucket C files get structure through the same interface as bucket A/B

**Acceptance Criteria (Gherkin)**
- Given `["Title", "", "Overview", "", "Body."]`, When I call `LabelHeadings().find_headings(lines)`, Then `[Heading(0, 1, "Title"), Heading(2, 2, "Overview")]`
- Given `["Title", "", "Parent", "Child label", "", "Body."]` (stacked), Then `[Heading(0, 1, "Title"), Heading(2, 2, "Parent"), Heading(3, 2, "Child label")]`
- Given `["", "Label"]` (no title), Then `[Heading(1, 2, "Label")]`
- Given `[]`, Then `[]`
- Given `LabelHeadings()`, Then it satisfies `HeadingDetector`
- Given every clean file, When I count headings per file and fingerprint them, Then it equals `tests/golden/label_fingerprint.json`; skipped if the data folder is missing

**Example with real data**
The listing in the PARSE-6 background: 20 headings for the scheduler file.

**Non-functional Requirements**
- Shared NFRs. Pure. `text` is the line stripped of surrounding whitespace, nothing else removed.

**Dependencies**
- APIs: `LabelHeadings` implementing `HeadingDetector`
- Uses: PARSE-4d `label_flags`, PARSE-5a `Heading`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-6b  detector_for  ✅

**Status:** Done (merged ea73de1)

**As a** chunker developer
**I want to** `detector_for(text)` to return the right detector for a file
**So that** the chunker asks one question and never sees bucket names

**Acceptance Criteria (Gherkin)**
- Given `"# Title\n\ntext"` (bucket A), When I call `detector_for(text)`, Then I get a `MarkdownHeadings`
- Given `"Title\n-----\n\ntext"` (bucket B), Then a `MarkdownHeadings`
- Given `"Overview\n\n- item"` (bucket C), Then a `LabelHeadings`
- Given `"Just prose."` or `""` (bucket D), Then a `LabelHeadings`
- Given the real corpus, When I count which detector each file gets, Then `MarkdownHeadings` 2,426 (A 1,645 + B 781) and `LabelHeadings` 2,763 (C 2,751 + D 12); skipped if the data folder is missing

**Example with real data**
`detector_for(<scheduler file text>)` is a `LabelHeadings`; `detector_for(<customer-security-questionnaire text>)` is a `MarkdownHeadings`.

**Non-functional Requirements**
- Shared NFRs. Pure. One `if`, no other logic.

**Dependencies**
- APIs: `detector_for(text: str) -> HeadingDetector`
- Uses: PARSE-3 `bucket`, PARSE-5b `MarkdownHeadings`, PARSE-6a `LabelHeadings`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-7  Blocks from markdown-it  (split into one function per PR)

**Background for all of PARSE-7**
Headings (PARSE-5/6) tell the chunker where sections start. Blocks tell it what must
not be cut in half: a list, a table, a code fence. markdown-it already knows the
boundaries of every block, so this story only reads them out.

How markdown-it reports blocks: `parse(text)` returns a flat token list. A top-level
block is a token with nesting `level == 0`, a line `map = [start, end)`, and a type that
does not end in `_close` (`paragraph_open` opens a paragraph; its `_close` twin carries
no map we need). Ten token types occur in the corpus; we map them to eight kinds:

| Token type | Kind | Blocks in corpus |
|---|---|---|
| `paragraph_open` | `text` | 119,459 |
| `bullet_list_open`, `ordered_list_open` | `list` | 110,824 |
| `heading_open` | `heading` | 39,807 |
| `hr` | `rule` | 5,253 |
| `table_open` | `table` | 3,740 |
| `fence`, `code_block` | `code` | 2,076 |
| `blockquote_open` | `quote` | 121 |
| `html_block` | `html` | 3 |

`end` is exclusive and, for lists, may include the trailing blank line (markdown-it's
map). Coverage check over the whole corpus: every non-blank line falls in exactly one
block, in all 5,189 files.

Bucket C note: a bare label such as `Overview:` is a one-line `text` block here.
`blocks` does not know about the label rule; the chunker (PARSE-8) uses the headings
list to treat that line as a heading. Line 0, the title, is likewise a `text` block.

Real example, `dsid_0012a01f…scheduler-health-oracle…txt`, first 12 blocks:
```
Block(kind='text',  start=0,  end=1)    'Scheduler Health Oracle and Self‑Heal Procedures'
Block(kind='text',  start=2,  end=3)    'Overview:'
Block(kind='text',  start=4,  end=5)    'This playbook defines the Scheduler Health Oracle ...'
Block(kind='text',  start=6,  end=7)    'Audience:'
Block(kind='list',  start=7,  end=11)   '- Oncall SREs and runtime engineers'  (3 items + trailing blank)
Block(kind='text',  start=11, end=12)   'Why SHO: problem statement'
Block(kind='list',  start=12, end=16)   '- Scheduler-level regressions ...'
Block(kind='text',  start=16, end=17)   'High-level design'
Block(kind='list',  start=17, end=23)   '1) Signal ingestion: ...'             (numbered list, 5 items)
Block(kind='text',  start=23, end=24)   'Detection signals and thresholds (baseline)'
Block(kind='list',  start=24, end=32)   '- kernel_cpu_latency_p50/p95/p99 ...'
Block(kind='text',  start=32, end=33)   'Policy mapping examples'
```
Golden check: `tests/golden/blocks_fingerprint.json`, sha256 over `<file> <block count>`
for all 5,189 files (281,283 blocks). Computed once with the v0 token walk.

Module: `pipeline/blocks.py`. Pure.

### PARSE-7a  Block value and the token-to-kind table  ⬜

**Status:** To do

**As a** chunker developer
**I want to** a `Block(kind, start, end)` value and one table `KIND_OF_TOKEN` from markdown-it token type to kind
**So that** the eight kinds are defined in exactly one place before any parsing code exists

**Acceptance Criteria (Gherkin)**
- Given `Block(kind="list", start=7, end=11)`, When I read its fields, Then `"list"`, `7`, `11`; it is frozen and compared by value
- Given `KIND_OF_TOKEN`, When I look up each of the ten token types in the table above, Then I get the kind in the same row
- Given a `Block`, When I ask `block.lines`, Then I get `end - start` (4 for the list above)
- Given `pipeline/blocks.py`, When I read it, Then it holds `Block`, `KIND_OF_TOKEN` and nothing else yet

**Example with real data**
`Block(kind="list", start=7, end=11)` is the `Audience:` bullet list in the scheduler file: lines 7, 8, 9 plus the blank line 10.

**Non-functional Requirements**
- Shared NFRs. Pure. Frozen dataclass; the table is a plain dict.

**Dependencies**
- APIs: `Block(kind: str, start: int, end: int)` with property `lines`; `KIND_OF_TOKEN: dict[str, str]`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-7b  blocks  ⬜

**Status:** To do

**As a** chunker developer
**I want to** `blocks(text)` to return every top-level block of a clean file, in line order
**So that** the chunker can keep lists, tables and code fences whole without knowing markdown-it tokens

**Acceptance Criteria (Gherkin)**
- Given a fenced code block on lines 10-14, When I call `blocks(text)`, Then one block is `Block("code", 10, 15)`
- Given a bullet list on lines 3-6 followed by a blank line and a paragraph, Then one `Block("list", 3, 7)` (markdown-it includes the trailing blank) and one `Block("text", 7, 8)`
- Given a pipe table with a separator row, Then one `Block("table", ...)` covering header, separator and rows
- Given two paragraphs separated by a blank line, Then two `text` blocks
- Given `## Scope`, Then `Block("heading", ...)` of one line
- Given a `#` inside a fence or a list inside a blockquote, Then no separate block for it (nested, level > 0)
- Given a token type not in `KIND_OF_TOKEN`, Then `blocks` raises `KeyError` naming the type (we would rather fail loudly than silently drop lines)
- Given `""`, Then `[]`
- Given every fixture file and every clean file, When I take the union of block line ranges, Then every non-blank line is covered exactly once
- Given every clean file, When I count blocks per file and fingerprint them, Then it equals `tests/golden/blocks_fingerprint.json`; skipped if the data folder is missing

**Example with real data**
The 12-block listing in the PARSE-7 background is `blocks(text)` on the scheduler file.

**Non-functional Requirements**
- Shared NFRs. Pure. markdown-it instance shared with `headings.py` (import `MARKDOWN` from there, do not create a second one).

**Dependencies**
- APIs: `blocks(text: str) -> list[Block]`
- Uses: PARSE-7a; `pipeline.headings.MARKDOWN`
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

---

## PARSE-12  Depth for label headings  ⬜

**Status:** Backlog (found while reviewing PARSE-6a on 2026-09-14)

**As a** RAG developer
**I want to** label headings to get a level from their depth signals (Step/Phase/numbered prefix, stacked labels, dotted numbers)
**So that** bucket C breadcrumbs keep their middle, e.g. `SDK Patch Release Playbook > Step-by-step playbook > Phase A`

**Acceptance Criteria (Gherkin)**
- Given `dsid_021076ec…sdk-patch-release-playbook…txt`, When I call `LabelHeadings().find_headings`, Then `Phase A … Phase D` are level 3 under `Step-by-step playbook: detailed procedure` (level 2)
- Given `dsid_006e117c…tenant-bootstrapping…txt`, Then `Pre-upgrade checks`, `Canary stages and validation gates`, `Ramped rollout`, `Rollback policy` are level 3 under `Step 3 — Immutable upgrade strategy`
- Given a file with no depth signals, Then the result is unchanged from today (title level 1, rest level 2)
- Given the corpus, Then the number of headings per file is unchanged (label golden still matches); only levels change

**Spot check, 2026-09-14** (all 2,763 label files, `LabelHeadings` output)

| Depth signal present in the file | Files |
|---|---|
| Stacked labels, child directly under parent (e.g. `FAQ` then `Q: How does ...`) | 748 |
| Numbered headings (`3) Escalation` style) | 208 |
| Dotted numbers (`1.2. Request and approval flow`) | 2 |

Random file `dsid_9679c592…slot-abort-contract…txt` shows the clearest case: ALL-CAPS
sections (`GOALS AND NON-GOALS`, `SIGNALING AND CONTRACT`) with Title-case sub-labels
directly under them (`Goals:`, `Non-goals:`, `Default timeouts (configurable):`). Today
all 26 are level 2; the caps/mixed-case switch is a fourth depth signal to consider.

Precision note from the same spot check, out of scope here but worth its own story: a few
flagged lines are not headings: `telemetry:` (a YAML key on the line after a heading),
`Artifact | Minimum window | Format ...` (a table header row with no leading pipe), and
`Emit standardized tracing annotations and metrics for every ...` (a sentence stacked
under a caps heading). Ties to the open item "30-file hand-labelled precision sample".

**Non-functional Requirements**
- Shared NFRs. Pure. To be split into one-function sub-stories when reached.

**Dependencies**
- Uses: PARSE-4, PARSE-6a
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-13  Document type from the title  ⬜

**Status:** Backlog (found 2026-09-14 while reviewing the dataset card: Confluence = "wikis, runbooks, and structured documentation")

**As a** RAG developer
**I want to** every node to carry a `doc_type` such as `playbook`, `runbook`, `policy`, taken from the page title
**So that** the retriever can filter or boost by kind (a "how do I roll back" question prefers runbooks over ADRs) and evaluation can be sliced by kind

**Background**
The dataset ships no type field (`data/confluence/manifest.json` is only a version
string). The first line of each clean file, the title, usually names the kind. Counted
over all 5,189 files, first matching keyword wins:

| Title contains | Files |
|---|---|
| playbook | 1,514 |
| runbook | 354 |
| guide | 305 |
| contract / spec | 353 |
| incident / postmortem | 135 |
| policy | 133 |
| checklist, ADR, onboarding, template, plan | 428 |
| no keyword | 1,652 (32%) |

This is retrieval metadata, not a parsing rule: it changes nothing in how a file is
cleaned, bucketed or chunked. It attaches in PARSE-9 when `TextNode`s are built.

**Acceptance Criteria (Gherkin)**
- Given `"Scheduler Health Oracle and Self-Heal Procedures"`, When I call `doc_type(title)`, Then `"procedure"`; given `"Postmortem: SEV-2 Dedicated autoscaler ..."`, Then `"postmortem"`; given a title with no keyword, Then `"unknown"`
- Given the keyword list, When I read it, Then it is one ordered tuple at the top of the module, first match wins
- Given a `TextNode` from PARSE-9, Then `metadata["doc_type"]` is set and excluded from embedding
- Given the corpus, Then the counts above are reproduced (skipped if the data folder is missing)

**Non-functional Requirements**
- Shared NFRs. Pure. To be split into one-function sub-stories when reached.

**Dependencies**
- APIs: `doc_type(title: str) -> str` in `pipeline/doc_type.py`
- Uses: PARSE-9
- Service Bus: N/A · Database: N/A · UI: N/A

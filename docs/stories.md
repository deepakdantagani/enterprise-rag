# Parsing stories

One story = one function = one PR (about 60 lines including its tests). Stories below
PARSE-2 are still module-level; each gets split into one-function sub-stories (a, b, c)
when we reach it, not before. Every sub-story carries an "Example with real data"
section: a before/after taken from the actual corpus, so the change is concrete. Each story is independent:
it can be built and merged without the others, because the existing modules keep
working until a later story switches the caller over. TDD on every story: write the
acceptance tests first (red), then the code (green), then the PR.

Shared non-functional requirements (apply to every story):
- Deterministic: same input, same output, no network, no model calls.
- Behaviour-preserving: after the story, `uv run python -m unittest discover tests` is
  green and the clean-folder manifest sha256 values are unchanged.
- Readable: top-of-file story, one idea per function, input -> output doctests, early returns.
- No Service Bus, database, or UI in any story below (marked N/A).

---

## PARSE-1  Text cleaning rules as a pure module

**As a** pipeline developer
**I want to** call the three cleaning rules (unescape, fix_structure, normalize) from a module that touches no files
**So that** the rules can be unit-tested and reused without a folder on disk

**Acceptance Criteria (Gherkin)**
- Given a string whose body is JSON-escaped, When I call `clean_text(raw)`, Then I get real newlines back and a flag `was_escaped=True`
- Given a normal string, When I call `clean_text(raw)`, Then the text is unchanged except whitespace tidy-up and `was_escaped=False`
- Given the module `pipeline/cleaning.py`, When I read its imports, Then it imports nothing that reads or writes files

**Dependencies**
- APIs: `clean_text(raw: str) -> CleanResult(text: str, was_escaped: bool)`; existing `is_escaped`, `unescape`, `fix_structure`, `normalize` keep their signatures
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-2  Corpus writer  (split into one function per PR)

### PARSE-2a  clean_one_file

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

**Dependencies**
- APIs: `clean_one_file(src: Path, dst: Path) -> CleanResult`  (uses PARSE-1 `clean_text`)

### PARSE-2b  manifest_row

**As a** pipeline developer
**I want to** `manifest_row(name, raw, result)` to build one manifest entry
**So that** the row shape is defined in exactly one place

**Acceptance Criteria (Gherkin)**
- Given a name, raw text and a CleanResult, When I call it, Then I get a dict with keys `file, raw_sha256, clean_sha256, was_escaped, raw_lines, clean_lines, raw_bytes, clean_bytes`
- Given the same inputs twice, Then the two dicts are equal

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

**Dependencies**
- APIs: `manifest_row(name: str, raw: str, result: CleanResult) -> dict`

### PARSE-2c  write_clean_corpus

**As a** pipeline developer
**I want to** `write_clean_corpus(raw_dir, clean_dir)` to run 2a over every `.txt` and save the rows from 2b as `_manifest.json`
**So that** one command produces the clean folder

**Acceptance Criteria (Gherkin)**
- Given a folder with two raw files, When I run it, Then two clean files and `_manifest.json` with two rows exist
- Given an empty folder, Then an empty manifest and no error
- Given the real raw folder, Then the fingerprint of the manifest equals `tests/golden/corpus_fingerprint.json`

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
Golden check: hash the lines `<file> <clean_sha256>` in order; it must equal `tests/golden/corpus_fingerprint.json`.

**Dependencies**
- APIs: `write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]`  (uses 2a, 2b)

---

## PARSE-3  Bucket classifier

**As a** pipeline developer
**I want to** ask one function which markup style a clean file uses
**So that** the chunker can pick the right heading detector

**Acceptance Criteria (Gherkin)**
- Given text with `# ` headings, When I call `bucket(text)`, Then I get `A_hash`
- Given text with underlined headings only, Then `B_setext`
- Given text with lists/tables/fences but no headings, Then `C_plain_labels`
- Given prose only or empty text, Then `D_prose`
- Given `pipeline/buckets.py`, When I read it, Then it contains `bucket` and its regexes and nothing else

**Dependencies**
- APIs: `bucket(text: str) -> str` (values above)
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-4  Label rule as its own module

**As a** pipeline developer
**I want to** the plain-label heading rule in `pipeline/label_rule.py` with only the rule and its helpers
**So that** the rule can be read, tested, and tuned without the debug and measurement code around it

**Acceptance Criteria (Gherkin)**
- Given the current `label_flags` tests, When I point them at `pipeline.label_rule`, Then they pass unchanged
- Given `pipeline/label_rule.py`, When I read it, Then it has no `explain`, no recall check, no corpus loop, no `__main__`
- Given a line with no blank line above and a non-label above, When I call `label_flags`, Then that line is not a heading

**Dependencies**
- APIs: `label_flags(lines: list[str]) -> list[bool]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-5  Heading detector interface + Markdown implementation

**As a** chunker developer
**I want to** call one `find_headings(lines)` method and get headings regardless of how they were written
**So that** the chunker never knows about `#`, underlines, or the label rule

**Acceptance Criteria (Gherkin)**
- Given lines with `## Scope` at index 4, When I call `MarkdownHeadings().find_headings(lines)`, Then I get `[Heading(line=4, level=2, text="Scope")]`
- Given `Scope` over `-----` at index 4, Then `[Heading(line=4, level=2, text="Scope")]` and the underline line is not a heading
- Given a `#` inside a fenced code block, Then it is not reported
- Given any detector, When I call it on `[]`, Then I get `[]`

**Dependencies**
- APIs: `Heading(line: int, level: int, text: str)`; `HeadingDetector` protocol with `find_headings(lines: list[str]) -> list[Heading]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-6  Label heading detector + selector

**As a** chunker developer
**I want to** a second detector that wraps the label rule, and one function that picks the detector for a file
**So that** adding a third way to find headings never touches the chunker

**Acceptance Criteria (Gherkin)**
- Given lines `["Title", "", "Overview", "", "Body."]`, When I call `LabelHeadings().find_headings(lines)`, Then I get `[Heading(0,1,"Title"), Heading(2,2,"Overview")]`
- Given a bucket-A text, When I call `detector_for(text)`, Then I get a `MarkdownHeadings`
- Given a bucket-C text, Then a `LabelHeadings`
- Given both detectors, When I run them on the same lines, Then both return `list[Heading]` sorted by line

**Dependencies**
- APIs: `LabelHeadings`, `detector_for(text) -> HeadingDetector`
- Uses: PARSE-3, PARSE-4, PARSE-5
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-7  Blocks from markdown-it

**As a** chunker developer
**I want to** the file as a list of top-level blocks with line ranges and a kind (text / list / table / code / quote)
**So that** the chunker can keep whole blocks together without knowing markdown-it tokens

**Acceptance Criteria (Gherkin)**
- Given a fenced code block on lines 10-14, When I call `blocks(text)`, Then one block has `kind="code", start=10, end=15`
- Given a bullet list on lines 3-6, Then one block with `kind="list"` covering exactly those lines
- Given a pipe table, Then one block `kind="table"`
- Given two paragraphs separated by a blank line, Then two `kind="text"` blocks
- Given the blocks for any fixture file, When I take the union of their line ranges, Then every non-blank line is covered exactly once

**Dependencies**
- APIs: `Block(kind: str, start: int, end: int)`; `blocks(text: str) -> list[Block]`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-8  Chunker

**As a** RAG developer
**I want to** turn blocks + headings into section-aware chunks, with no LlamaIndex in the module
**So that** the chunking logic is testable on plain strings

**Acceptance Criteria (Gherkin)**
- Given headings at lines 2 and 8 and blocks in between, When I call `chunk(lines, blocks, headings, max_chars)`, Then no chunk spans a heading
- Given a list block larger than `max_chars`, Then it is emitted as one chunk on its own, never split
- Given blocks that together fit in `max_chars`, Then they are packed into one chunk
- Given a heading followed directly by another heading, Then the second one's path includes the first
- Given every fixture file, Then every non-blank non-heading line is in exactly one chunk

**Dependencies**
- APIs: `Chunk(start: int, end: int, heading_path: list[str], block_kinds: list[str])`; `chunk(...) -> list[Chunk]`
- Uses: PARSE-5, PARSE-7
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-9  LlamaIndex adapter

**As a** RAG developer
**I want to** a `NodeParser` that wraps the chunker and produces `TextNode`s
**So that** the pipeline plugs into LlamaIndex without the chunker depending on it

**Acceptance Criteria (Gherkin)**
- Given a `Document`, When I call `ConfluenceNodeParser().get_nodes_from_documents([doc])`, Then each node's text starts with `"<title> > <section>\n\n"` and metadata has `line_start`, `line_end`, `heading_path`
- Given `nodes.py`, When I read it, Then it contains no chunking rules, only the mapping `Chunk -> TextNode`
- Given the current `test_nodes.py`, Then it passes unchanged

**Dependencies**
- APIs: `ConfluenceNodeParser(max_chars=1600)`
- Uses: PARSE-6, PARSE-7, PARSE-8
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-10  Triage gate on the new modules

**As a** data owner
**I want to** the triage gate to use the new modules and keep its current flags
**So that** new exports are checked the same way after the refactor

**Acceptance Criteria (Gherkin)**
- Given the raw corpus, When I run `python -m pipeline.triage`, Then `_triage.json` lists the same 117 files with the same flags as before the refactor
- Given a folder with one escaped and one normal file, When I run triage on it, Then it exits 0 and flags nothing

**Dependencies**
- Uses: PARSE-2, PARSE-3, PARSE-4
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-11  Debug and measurement tools out of the pipeline

**As a** pipeline developer
**I want to** `explain` and the recall self-check under `tools/`, not `pipeline/`
**So that** `pipeline/` contains only code that data flows through

**Acceptance Criteria (Gherkin)**
- Given `tools/explain.py <file>`, When I run it, Then I get the per-line HEADING / reason table
- Given `tools/measure.py`, When I run it, Then I get the bucket counts and the recall number
- Given `pipeline/`, When I grep for `explain` or `recall_against`, Then there are no matches

**Dependencies**
- Uses: PARSE-3, PARSE-4
- Service Bus: N/A · Database: N/A · UI: N/A

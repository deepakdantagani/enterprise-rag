# Chunking stories

Chunking is library code: LlamaIndex's `MarkdownNodeParser` cuts at `#` headings and
`SentenceSplitter` trims the few sections over budget (PARSE-9). Our part, PARSE-8, is
one pass per clean file that writes the `#`s, so every page is proper Markdown and one
library chunker serves all three heading styles. Design and evidence: [chunker design](../design/2-chunker-system-design.md).

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

## Build order and one-liners

| # | Story | One line |
|---|---|---|
| 0 | PARSE-17 heading truth set | 10 real files, each picked because it breaks one assumption, with the true heading lines decided by a person; 8a and 8b are tested against it |
| 1 | PARSE-8a structure | markdown-it in one call: which lines are `#` or underlined headings (with level) and which line ranges are code or table |
| 2 | PARSE-8b1 label_lines | which label-rule lines become headings: never inside code or a table, never a `Q:` line, never directly under another heading, and only when the file has more labels than Markdown headings |
| 2 | PARSE-8b2 to_markdown | one pass per file: `#` lines kept, underlined headings rewritten, `label_lines` get `##`, line 0 is the title, same line count |
| 3 | PARSE-8c markdown copy + manifest | write `data/confluence/markdown/<file>.md` for every clean file, record `md_sha256` and `rewritten_lines` |
| 4 | PARSE-8d retire the old heading modules | fingerprint `to_markdown` over the corpus, explain every difference against the old heading goldens, then delete `buckets.py`, `headings.py`, `blocks.py` and their goldens |

---

## PARSE-17  Heading truth set: real files with hand-checked headings  ✅

**Status:** Done 2026-09-17. 10 files, 175 true headings, 42 known gaps (6 after PARSE-8b1).

**Background**
Every heading rule is an assumption about how people write pages, and on 5,189 pages
every assumption is wrong somewhere. Unit tests on made-up strings only prove the rule
does what we imagined. So for each assumption we also assume the opposite, count it on
the corpus, and keep one real file that shows it. Counts on 2026-09-16:

| We assume | Times it is wrong | Real example | Today |
|---|---|---|---|
| `---` under text is an underlined heading | 191 (text is 2+ lines) | `Appendices` / `A: Example YAML` / `---` opens a YAML block | handled: one-line guard (8a) |
| `---` under one line is a heading | about 160 | `Schema snippet (YAML) for slice manifest:` / `-----` / `slice_id: ...` | harmless: the rule opens a YAML block, but the line above it is a real label, so the heading is right; only the rule line is blanked |
| a heading inside a list or quote is not real | 216, guard right every time | `- p95 latency (PromQL):` / `  -` | handled: top-level guard (8a) |
| a line starting `# ` is a heading | about 50 | `# provision-basic-access.sh ...`, a bash comment after `#!/bin/bash`, no fence | known gap, counted by PARSE-14 |
| a bare label or a whole-line bold is a section | wrong on pages whose author wrote `##`: 24 false headings on one runbook | `**Mitigation**` inside `### A) ...`, `Out of scope:` inside `## Scope` | known gap: the label rule over-fires on `#` pages; decide in PARSE-8b |
| a `Q:` line is a section | 1,155 lines in 453 files | `Q: Who can ...` under `FAQs:`; a whole FAQ is about 107 tokens, one context | known gap: decide in PARSE-8b |
| labels end with `:` | not assumed | `Appendices`, `Configuration examples` are flagged without a colon | handled (PARSE-4d) |

The truth is decided by a person reading the page, never produced by the code under
test; otherwise the test only proves the code agrees with itself. Files 1 to 5 were
decided line by line with Deepak; 6 to 10 by Claude with the same rules, for review in
the PR. The rules that came out of it:

1. A sentence is never a heading, even when it starts bold or with `Note:`.
2. The author's strongest heading style marks the sections. On a page with `##` or
   underlines, a bare label or bold line is a lead-in. On a page with only labels, a
   standalone label after a blank line with content under it is a section.
3. Same context, no cut: an FAQ with its `Q:`/`A:` lines, a lead-in directly under a
   heading, the bold parts of one `###` scenario that fits a chunk.
4. Sample content (a template, a message draft) is not this page's structure.
5. A comment in unfenced code is not a heading.
6. For bare labels the level is a guess, so tests compare label headings by line only;
   levels are compared where the author wrote them (`#`, `=`, `-`).

**As a** pipeline developer
**I want to** a small set of real clean files with the true heading lines written down by hand
**So that** `structure` and `to_markdown` are tested against what a reader sees, and every known gap is a visible, counted entry instead of a surprise

**Acceptance Criteria (Gherkin)**
- Given `tests/fixtures/headings/`, Then it holds one real clean file per row below, copied byte for byte (`source` names the clean file, and a test compares the bytes when the corpus is present), and one `expected.json`
- Given `expected.json`, Then each file has `why` (the assumption it breaks), `headings` (`{line: level}`, the truth), and `known_gaps` (`{line: reason}`, lines where the current design is knowingly wrong: a false heading when the line is not in `headings`, a missed one when it is)
- Given every fixture file, Then every line number in `headings` and `known_gaps` exists in the file and is not blank
- Given a truth heading line, Then it is never inside a fence or table of that file (a person would not call a table row a heading)
- Given `load_truth()`, Then it returns the entries in name order, and is the only way tests read the set
- Given `disagreements(reported, truth)`, Then it lists every line where the reported heading lines differ from the truth, known gaps excused; a known gap that no longer differs is listed too, with "remove this known gap". PARSE-8b asserts the list is empty. PARSE-8a, which only sees `#` and underlined headings, asserts `reported - truth - known_gaps` is empty

Files (10):

| Fixture | Shows |
|---|---|
| 01_hash_page_with_table | baseline `#` page; bold sentence starts are not headings |
| 02_underlined_page_with_lead_in | underlined sections; `Key goals:` is a lead-in (1 gap) |
| 03_label_page_with_table | labels are the only style, so they are the sections |
| 04_labels_with_template_block | a template's labels and stray `##` are sample content; FAQ is one section (3 gaps) |
| 05_no_headings_yaml_between_rules | the export lost all headings; YAML between two `---` must not become one |
| 06_labels_without_colons_appendix | two-line "underlined heading" rejected; appendix parts A to D; code comment as `#` (7 gaps) |
| 07_rule_opens_yaml_under_label | `-----` opening YAML under a real label; the YAML itself must not become a heading |
| 08_dash_under_list_item | `-` under a list item reads as a nested heading (2 gaps, both `Q:`) |
| 09_bash_comments_unfenced | bash comments read as `#` headings (5 gaps) |
| 10_hash_page_with_bold_and_labels | the label rule over-fires on a `##` page (24 gaps) |

**Example with real data**
```json
"02_underlined_page_with_lead_in.txt": {
  "source": "dsid_10912e04...__platform-operational-contracts-and-oncall-playbook-2026.txt",
  "why": "The author underlines real sections. 'Key goals:' is not underlined: a lead-in ...",
  "headings": {"0": 1, "2": 2, "12": 2, "16": 2},
  "known_gaps": {"6": "'Key goals:' is a lead-in; the label rule flags it"}
}
```
A prototype of today's design (markdown-it with both 8a guards, plus the label rule
outside fences and tables) gives zero disagreements on all 10 files once the 42 known
gaps are excused, so the gap list is complete for this set.

**Non-functional Requirements**
- Shared NFRs. No pipeline code. `tests/truth.py` is about 50 lines: a frozen `Truth`, `load_truth`, `disagreements`. Fixture files are committed (the corpus under `data/` is not), so the tests run on a fresh clone.
- Adding a file later is one copy plus one JSON entry; no test code changes.

**Dependencies**
- APIs: `load_truth() -> list[Truth(name, source, why, text, headings: dict[int, int], known_gaps: dict[int, str])]`, `disagreements(reported: set[int], truth: Truth) -> list[str]`
- Uses: clean files from PARSE-3
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-8  Every clean file becomes Markdown, one pass per file  (split into one function per PR)

**Background for all of PARSE-8**
Only 32% of pages write headings as `#`. 15% underline them (`Summary` over `-------`),
53% write bare labels (`Overview:`). LlamaIndex's `MarkdownNodeParser` only sees `#`
lines: on a label or underlined page it returns the whole page as one node. So before
chunking we write the `#`s ourselves, file by file, and save the result.

Design rules, each one a test:
1. **The majority style marks the sections.** Labels count only when the file has
   more label lines than Markdown headings. One stray `## - 2026-01-12` inside a
   template no longer hides 20 labels (the old file-level bucket did, 256 files), and
   a runbook written in `##` no longer gets 24 false headings from its lead-ins and
   bold lines (what running the label rule everywhere did). Scored on the PARSE-17
   truth set: labels everywhere 42 wrong lines, labels only when no Markdown heading
   92, majority 17; with rule 4 below, 6.
2. **Same line count.** A heading line gets `#`s in front; an underline becomes an
   empty line. "Lines 4 to 5" means the same lines in raw, clean and markdown.
3. **Never inside code or a table.** markdown-it says which line ranges are fences or
   tables; the label rule is not consulted there.
4. **Same context, no cut.** A `Q:` line is never a heading: a whole FAQ is about 107
   tokens (median, 453 files), one chunk. A label directly under another heading, no
   blank line between, is a lead-in (`Tier definitions:` under `Compression tiers`;
   1,831 lines in 849 files).
   **Levels.** `#` lines keep theirs. An underline of `=` is level 1, `-` level 2. A
   label is level 2: for a bare label the level is a guess, so we do not guess deeper.
   Line 0, when it is not a heading already, is the title, level 1.
5. **Deterministic and reproducible.** Same clean file, same markdown; the manifest
   records its sha256; the folder can be deleted and rebuilt.

Three small pure pieces, one reason to change each:
```
structure(text)              markdown-it: heading lines + protected ranges      changes only if the parser changes
label_flags(lines)           the heuristic, exists (PARSE-4d)                   changes whenever we tune the rule
label_lines(lines, found)    which flagged lines count on this page             changes when rules 1, 3 or 4 change
to_markdown(text)            writes the #s, nothing else                        changes only if the output format changes
```

Real examples:
```
scheduler page (labels)      clean line 2  Overview:      →  ## Overview:          143 lines in, 143 out
autotune playbook (underl.)  clean line 2  Summary        →  ## Summary            144 lines in, 144 out
                             clean line 3  ---            →  (empty)
runbook guidelines (mixed)   20 labels + 1 stray `##` + 1 underline → 22 headings, was 3
```
Measured with the prototype: 20 sections on the scheduler and privilege pages, 20 on
the autotune playbook, 6 on the ADR sample, every node's line range recovered.

Module: `pipeline/to_markdown.py`. Pure. File writing lives in PARSE-8c.

### 1. PARSE-8a  structure  ✅

**Status:** Done 2026-09-17. Corpus: 39,623 headings (12,427 underlined), 6,081 protected ranges, 3,004 files where markdown-it sees no heading.

**As a** pipeline developer
**I want to** `structure(text)` to return the heading lines markdown-it sees, with level, and the line ranges that are code fences or tables
**So that** `to_markdown` gets both facts from one parse, and the label rule is never applied inside a fence or table

**Acceptance Criteria (Gherkin)**
- Given `"# T\n\n## A\ntext"`, Then headings `{0: 1, 2: 2}` and no protected ranges
- Given `"Summary\n-------\ntext"`, Then headings `{0: 2}` and `underlines == {1}`
- Given `"Title\n=====\n"`, Then headings `{0: 1}`
- Given a fenced block on lines 3-6 and a pipe table on lines 9-12, Then `protected == [(3, 7), (9, 13)]`
- Given a `#` line inside the fence, Then it is not in `headings`
- Given `"---\nroute: a\nmodel: b\n---\n"` (a YAML block between two `---` lines), Then `headings == {}` and `underlines == set()`. An underlined heading counts only when its text is one line. Markdown reads a `---` under a multi-line paragraph as a heading over the whole paragraph; in this corpus that is always a config block (191 cases in 182 files, against 12,461 real one-line underlined headings), so `to_markdown` must leave those lines alone
- Given a heading inside a quote (`> # quoted`), Then it is not in `headings`; given a fence inside a list item, Then its range is still in `protected`
- Given the PARSE-17 truth set, Then `structure` reports no heading that is not a true heading or a listed known gap, its levels equal the truth's where both have the line, and no true heading lies inside a protected range
- Given every clean file, Then the per-file counts of headings, underlines and protected ranges fingerprint to `tests/golden/structure_fingerprint.json`. The totals are not expected to equal the old `markdown_headings_fingerprint`: that one also counts the title line and the multi-line underlined headings; PARSE-8d explains the difference

**Example with real data**
Autotune playbook: 20 setext headings at lines 2, 6, 11, …, each with its underline line; no fences. Onboarding PRD: 28 `#` headings, none inside a fence.

**Non-functional Requirements**
- Shared NFRs. Pure. About 25 lines: one walk over the markdown-it token stream using `token.map`. Uses the shared `MARKDOWN` instance.

**Dependencies**
- APIs: `structure(text: str) -> Structure(headings: dict[int, int], underlines: set[int], protected: list[tuple[int, int]])`
- Uses: `pipeline/markdown.py`
- Service Bus: N/A · Database: N/A · UI: N/A

### 2. PARSE-8b1  label_lines  ✅

**Status:** Done 2026-09-17. Corpus: 74,131 label lines in 3,591 files; 30 files have no heading besides the title. Truth set: 36 known gaps fixed and removed, 6 left (a stray `##` in a template, two appendix parts nothing finds, three code comments read as `#`).

**As a** pipeline developer
**I want to** `label_lines(lines, found)` to return the label-rule lines that are sections of this page
**So that** `to_markdown` only writes `##` where a reader sees a section, and every "is this label a heading" rule lives in one function

**Acceptance Criteria (Gherkin)**
- Given `["Title", "", "Overview:", "text"]` and no Markdown headings, Then `{2}` (line 0 is the title, never a label line)
- Given a label-shaped line inside a fence or table range of `found`, Then it is not returned
- Given a line that `found.headings` already has, Then it is not returned (it is a heading already)
- Given `Q: Why?`, `Q1: Why?` or `Q) Why?` flagged by the label rule, Then it is not returned
- Given `FAQs:` on line 4 and a flagged label on line 5, Then 5 is not returned (directly under a heading); the same when line 4 is a `#` or underlined heading from `found`; with a blank line between them, it is returned
- Given 3 Markdown headings and 1 label, Then `set()`; given 1 Markdown heading and 20 labels, Then all 20; given a tie, Then `set()` (the author's Markdown wins)
- Given the PARSE-17 truth set, Then `{0} | found.headings | label_lines` disagrees with the truth on exactly the known gaps, and the known gaps this story fixes are removed from `expected.json` (36 of 42: the lead-in on file 2, the `Q:` lines, the two lead-ins on file 6, all 24 on file 10)
- Given every clean file, Then the per-file counts fingerprint to `tests/golden/label_lines_fingerprint.json`

**Example with real data**
Audit-log incident runbook (35 `##`/`###` headings, 24 flagged lines): `set()`. Runbook authoring guidelines (2 Markdown headings, 23 flagged lines): 20 lines, without `Q:` lines 128 and 131. Corpus: 1,281 files where Markdown wins (10,020 label lines not promoted), 619 where labels win, 50 within 2 of a tie; PARSE-8d samples from those.

**Non-functional Requirements**
- Shared NFRs. Pure. About 25 lines, in `pipeline/to_markdown.py`.

**Dependencies**
- APIs: `label_lines(lines: list[str], found: Structure) -> set[int]`
- Uses: PARSE-8a `Structure`, PARSE-4d `label_flags`, PARSE-17 truth set
- Service Bus: N/A · Database: N/A · UI: N/A

### 2. PARSE-8b2  to_markdown  ✅

**Status:** Done 2026-09-17. Corpus: 118,943 headings written or kept in 5,189 files, 104,174 lines changed, same line count in every file, no heading we meant is missed by markdown-it.

**As a** pipeline developer
**I want to** `to_markdown(text)` to return the clean text with `#`s on every heading line, one pass, same line count
**So that** LlamaIndex's `MarkdownNodeParser` sees every section on every page style

**Acceptance Criteria (Gherkin)**
- Given `"Overview:\n\ntext"`, Then `"# Overview:\n\ntext"` (line 0 with no heading is the title, level 1)
- Given `"Title\n\nOverview:\n\ntext"`, Then `"# Title\n\n## Overview:\n\ntext"`
- Given `"Summary\n---\ntext"`, Then `"## Summary\n\ntext"` (underline emptied, not removed)
- Given `"# Title\n\n## A\ntext"`, Then unchanged
- Given an empty text, or a blank line 0, Then no title is written
- Given any input, Then the output has exactly as many lines as the input
- Given any input, Then only heading lines and underline lines differ from the input
- Given a rewritten heading that was indented, Then the indentation is dropped (`  Summary` becomes `## Summary`), so the `#` is at the start of the line where `MarkdownNodeParser` looks
- Given the PARSE-17 truth set, Then the `#` lines of the output (start of line, outside fences: what `MarkdownNodeParser` reads) disagree with the truth on exactly the known gaps
- Given every clean file, Then every heading we meant is a top-level heading for markdown-it in the output, and the corpus fingerprints to `tests/golden/markdown_fingerprint.json`

Not a goal: running `to_markdown` on its own output. PARSE-8c always writes from the clean file. It is not idempotent in 20 files: once `Appendices` is `## Appendices`, the paragraph above a YAML `---` is one line shorter and markdown-it reads `A: Example YAML` over `---` as an underlined heading (14 lines), or an indented `# comment` as a heading (8 lines). The golden pins that count at 22. `MarkdownNodeParser` sees none of them.

**Example with real data**
Scheduler page: 20 heading lines rewritten, 123 untouched, 143 out. Autotune playbook: 20 underlined headings become `##`, 20 underline lines emptied, 144 lines in and out.

**Non-functional Requirements**
- Shared NFRs. Pure. About 20 lines: `structure`, `label_lines`, then write.

**Dependencies**
- APIs: `to_markdown(text: str) -> str`
- Uses: PARSE-8a `structure`, PARSE-8b1 `label_lines`
- Service Bus: N/A · Database: N/A · UI: N/A

### 3. PARSE-8c  Markdown copy and manifest columns  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** the corpus writer to save `data/confluence/markdown/<same name>.md` for every clean file and add `md_sha256` and `rewritten_lines` to each manifest row
**So that** anyone can open the exact file that was chunked, diff it against clean, and prove only heading lines differ

**Acceptance Criteria (Gherkin)**
- Given a clean file, When the writer runs, Then `data/confluence/markdown/<name>.md` exists with the same line count
- Given the manifest row for that file, Then it has `md_sha256` and `rewritten_lines` (lines that differ from clean)
- Given a run over the corpus twice, Then every `md_sha256` is identical
- Given the existing manifest columns and the clean-folder golden, Then unchanged (clean files are not touched)
- Given a file with no headings at all, Then `rewritten_lines` is 1 (the title) and the rest equals the clean file

**Example with real data**
Scheduler page: `"rewritten_lines": 20`. Autotune playbook: `40` (20 headings + 20 underlines).

**Non-functional Requirements**
- Shared NFRs. One pass over the corpus, under 30 s. The markdown folder is derived data: gitignored, rebuildable, never edited by hand.

**Dependencies**
- APIs: `write_markdown(clean_dir: Path, markdown_dir: Path, manifest: Path) -> None`, next to PARSE-2's functions
- Uses: PARSE-2, PARSE-8b
- Service Bus: N/A · Database: N/A · UI: N/A

### 4. PARSE-8d  Retire buckets, headings and blocks  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** delete `pipeline/buckets.py`, `headings.py`, `blocks.py`, their tests and their three goldens, once `to_markdown` is accepted
**So that** there is one way to find a heading, not two

**Acceptance Criteria (Gherkin)**
- Given the corpus, When I compare `to_markdown`'s headings against the old detectors' headings per file, Then every file that differs is in one of three explained groups, each with a count in the PR: labels now found on `#` pages, headings now found on pages the old bucket flipped, stacked-label levels
- Given a random 30 of the "labels now found on `#` pages" additions, When read by hand, Then at most 3 are not headings, or the label rule is tuned first
- Given the three modules removed, Then `uv run python -m unittest discover tests` is green and `pipeline/` contains only `cleaning`, `corpus`, `manifest`, `label_rule`, `markdown`, `to_markdown` (and later `nodes`)
- Given `docs/`, Then no story or design still names a removed module as current

**Example with real data**
Runbook guidelines: old 3 headings, new 22. Group: "bucket flipped by a stray `##`". Onboarding PRD: old 28, new 28 (+0 labels), no change.

**Non-functional Requirements**
- Shared NFRs. The diff script lives under `tools/` and is deleted with the PR; its output table goes in the PR description.

**Dependencies**
- Uses: PARSE-8b, PARSE-8c
- Service Bus: N/A · Database: N/A · UI: N/A

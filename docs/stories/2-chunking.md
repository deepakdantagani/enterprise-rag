# Chunking stories

Chunking is library code: LlamaIndex's `MarkdownNodeParser` cuts at `#` headings and
`SentenceSplitter` trims the few sections over budget (PARSE-9). Our part, PARSE-8, is
one pass per clean file that writes the `#`s, so every page is proper Markdown and one
library chunker serves all three heading styles. Design and evidence: [chunker design](../design/2-chunker-system-design.md).

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

## Build order and one-liners

| # | Story | One line |
|---|---|---|
| 0 | PARSE-17 heading truth set | about 11 real files, each picked because it breaks one assumption, with the true heading lines decided by a person; 8a and 8b are tested against it |
| 1 | PARSE-8a structure | markdown-it in one call: which lines are `#` or underlined headings (with level) and which line ranges are code or table |
| 2 | PARSE-8b to_markdown | one pass per file: `#` lines kept, underlined headings rewritten, label-rule lines get `##` (`###` when stacked under an empty label), nothing inside code or a table, same line count |
| 3 | PARSE-8c markdown copy + manifest | write `data/confluence/markdown/<file>.md` for every clean file, record `md_sha256` and `rewritten_lines` |
| 4 | PARSE-8d retire the old heading modules | fingerprint `to_markdown` over the corpus, explain every difference against the old heading goldens, then delete `buckets.py`, `headings.py`, `blocks.py` and their goldens |

---

## PARSE-17  Heading truth set: real files with hand-checked headings  ⬜

**Status:** To do. Built before PARSE-8a.

**Background**
Every heading rule is an assumption about how people write pages, and on 5,189 pages
every assumption is wrong somewhere. Unit tests on made-up strings only prove the rule
does what we imagined. So for each assumption we also assume the opposite, count it on
the corpus, and keep one real file that shows it. Counts on 2026-09-16:

| We assume | Times it is wrong | Real example | Today |
|---|---|---|---|
| `---` under text is an underlined heading | 191 (text is 2+ lines) | `Appendices` / `A: Example YAML` / `---` opens a YAML block | handled: one-line guard (8a) |
| `---` under one line is a heading | about 160 | `Schema snippet (YAML) for slice manifest:` / `-----` / `slice_id: ...` | known gap |
| a heading inside a list or quote is not real | 216, guard right every time | `- p95 latency (PromQL):` / `  -` | handled: top-level guard (8a) |
| a line starting `# ` is a heading | about 50 | `# provision-basic-access.sh ...`, a bash comment after `#!/bin/bash`, no fence | known gap, counted by PARSE-14 |
| a whole-line bold is found by the label rule | 770 of 4,127 missed | `**Symptoms**` directly under `### A) ...` | known gap |
| labels end with `:` | not assumed | `Appendices`, `Configuration examples` are flagged without a colon | handled (PARSE-4d) |

The truth is decided by a person reading the page, never produced by the code under
test; otherwise the test only proves the code agrees with itself. Claude proposes the
heading lines per file, Deepak approves them in the PR.

**As a** pipeline developer
**I want to** a small set of real clean files with the true heading lines written down by hand
**So that** `structure` and `to_markdown` are tested against what a reader sees, and every known gap is a visible, counted entry instead of a surprise

**Acceptance Criteria (Gherkin)**
- Given `tests/fixtures/headings/`, Then it holds one real clean file per row below, copied byte for byte, and one `expected.json`
- Given `expected.json`, Then each file has `why` (the assumption it breaks), `headings` (`{line: level}`, the truth), and `known_gaps` (`{line: reason}`, lines where the current design is knowingly wrong)
- Given every fixture file, Then every line number in `headings` and `known_gaps` exists in the file and is not blank
- Given a truth heading line, Then it is never inside a fence or table of that file (a person would not call a table row a heading)
- Given `load_truth()`, Then it returns `[(name, text, headings, known_gaps)]` in name order, and is the only way tests read the set
- Given PARSE-8a and 8b tests, Then they use it this way: a reported heading that is not in the truth fails the test unless the line is in `known_gaps`; a line in `known_gaps` that starts passing also fails, with the message "remove this known gap"

Files (11):

| Fixture | Breaks the assumption |
|---|---|
| zero-retention requests | none: plain `#` page with a table (the baseline) |
| platform operational contracts | underlined page that also has a bare label (`Key goals:`) |
| quiet cutovers runbook | bare-label page with a table |
| runbook authoring guidelines | 20 labels, one stray `##`, one underline |
| model promotion protocol | YAML block between two `---` lines |
| probe telemetry plan | `---` opens YAML under a two-line paragraph |
| slice budgeting contract | `-----` opens YAML under a one-line lead-in (known gap) |
| synthetic canary capacity | `-` under a list item reads as a nested heading |
| contributor foundations | bash comments after `#!/bin/bash`, no fence (known gap) |
| audit-log incident runbook | `**Symptoms**` bold sub-headings (known gap) |
| one prose page from the 12 with no headings | no headings at all |

**Example with real data**
```json
"slice-budgeting.txt": {
  "why": "----- under a one-line lead-in opens a YAML block, it is not an underline",
  "headings": {"0": 1, "12": 2, "...": 2},
  "known_gaps": {"81": "markdown-it reads line 81 as an underlined heading; about 160 in the corpus"}
}
```

**Non-functional Requirements**
- Shared NFRs. No pipeline code. `tests/truth.py` is about 15 lines. Fixture files are committed (the corpus under `data/` is not), so the tests run on a fresh clone.
- Adding a file later is one copy plus one JSON entry; no test code changes.

**Dependencies**
- APIs: `load_truth() -> list[Truth(name, text, headings: dict[int, int], known_gaps: dict[int, str])]`
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
1. **Every line is judged on its own.** No file-level "bucket": a page mixing `#`,
   underlines and labels gets all three recognised. (The old file-level decision let
   one stray `## - 2026-01-12` inside a template hide 20 labels; 256 files, 5%.)
2. **Same line count.** A heading line gets `#`s in front; an underline becomes an
   empty line. "Lines 4 to 5" means the same lines in raw, clean and markdown.
3. **Never inside code or a table.** markdown-it says which line ranges are fences or
   tables; the label rule is not consulted there.
4. **Levels.** `#` lines keep theirs. An underline of `=` is level 1, `-` level 2. A
   label is level 2, or level 3 when the previous non-blank line is a label with no
   content of its own (`FAQ` over `Q: How does ...`), which reproduces the v0
   breadcrumbs `Title > FAQ > Q: ...`. Line 0, when it is not a heading already, is
   the title, level 1.
5. **Deterministic and reproducible.** Same clean file, same markdown; the manifest
   records its sha256; the folder can be deleted and rebuilt.

Three small pure pieces, one reason to change each:
```
structure(text)              markdown-it: heading lines + protected ranges      changes only if the parser changes
label_flags(lines)           the heuristic, exists (PARSE-4d)                   changes whenever we tune the rule
to_markdown(text)            composes both, writes the #s                       changes only if the rules above change
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

### 1. PARSE-8a  structure  ⬜

**Status:** To do

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
- Given every clean file, Then the per-file counts of headings, underlines and protected ranges fingerprint to `tests/golden/structure_fingerprint.json`. The totals are not expected to equal the old `markdown_headings_fingerprint`: that one also counts the title line and the multi-line underlined headings; PARSE-8d explains the difference

**Example with real data**
Autotune playbook: 20 setext headings at lines 2, 6, 11, …, each with its underline line; no fences. Onboarding PRD: 28 `#` headings, none inside a fence.

**Non-functional Requirements**
- Shared NFRs. Pure. About 25 lines: one walk over the markdown-it token stream using `token.map`. Uses the shared `MARKDOWN` instance.

**Dependencies**
- APIs: `structure(text: str) -> Structure(headings: dict[int, int], underlines: set[int], protected: list[tuple[int, int]])`
- Uses: `pipeline/markdown.py`
- Service Bus: N/A · Database: N/A · UI: N/A

### 2. PARSE-8b  to_markdown  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** `to_markdown(text)` to return the clean text with `#`s on every heading line, one pass, same line count
**So that** LlamaIndex's `MarkdownNodeParser` sees every section on every page style

**Acceptance Criteria (Gherkin)**
- Given `"Overview:\n\ntext"`, Then `"# Overview:\n\ntext"` (line 0 with no heading is the title, level 1)
- Given `"Title\n\nOverview:\n\ntext"`, Then `"# Title\n\n## Overview:\n\ntext"`
- Given `"Summary\n---\ntext"`, Then `"## Summary\n\ntext"` (underline emptied, not removed)
- Given `"# Title\n\n## A\ntext"`, Then unchanged
- Given `"Title\n\nFAQ\nQ: Why?\n\nBecause."`, Then `FAQ` is `##` and `Q: Why?` is `###` (stacked label rule); with a blank line between them, still `###`
- Given a label-shaped line inside a fenced block or a table, Then unchanged
- Given a page with one stray `## x` line and twenty `Label:` lines, Then all twenty-one are headings
- Given any input, Then the output has exactly as many lines as the input
- Given every clean file, Then `MarkdownNodeParser` on the output yields one node per heading with a body, and the corpus fingerprints to `tests/golden/markdown_fingerprint.json`

**Example with real data**
Scheduler page: 20 heading lines rewritten, 123 untouched, 143 out. Runbook guidelines: 22 headings (20 labels, the stray `##`, one underline), where the old file-level bucket found 3.

**Non-functional Requirements**
- Shared NFRs. Pure. About 30 lines: `structure` + `label_flags`, then one `for` over the lines.

**Dependencies**
- APIs: `to_markdown(text: str) -> str`
- Uses: PARSE-8a `structure`, PARSE-4d `label_flags`
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

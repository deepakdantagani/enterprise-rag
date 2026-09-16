# Chunking stories

Chunking is library code: LlamaIndex's `MarkdownNodeParser` cuts at `#` headings and
`SentenceSplitter` trims the few sections over budget (PARSE-9). Our part, PARSE-8, is
the step that makes every clean file proper Markdown first, so one chunker serves all
three heading styles. Design and evidence: [chunker design](../design/2-chunker-system-design.md).

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

## Build order and one-liners

| # | Story | One line |
|---|---|---|
| 1 | PARSE-8a markdown_view | write `#`×level in front of every heading our detector found, blank a setext underline, skip lines inside tables and code; same line count out |
| 2 | PARSE-8b markdown copy + manifest | write `data/confluence/markdown/<file>.md` for every clean file and record `md_sha256` and `rewritten_lines` in the manifest |

---

## PARSE-8  Markdown view: make every clean file proper Markdown  (split into one function per PR)

**Background for all of PARSE-8**
Only 32% of pages write headings as `#`. 15% underline them (`Summary` over `-------`,
a setext heading), 53% write bare labels (`Overview:`). Our detector (PARSE-5/6) finds
all three and returns `(line, level, text)`. LlamaIndex's `MarkdownNodeParser` only
sees `#` lines: on a label or underlined page it returns the whole page as one node.
So before chunking, we write the `#`s ourselves. After this step every page is Markdown
and one library chunker serves all of them.

Three rules keep citations honest:
1. **Same line count.** A heading line gets `#`s in front; a setext underline becomes an
   empty line. No line is added or removed, so "lines 4 to 5" means the same lines in
   raw, clean and markdown.
2. **Never inside a table or code block.** The label rule cannot see block structure and
   sometimes flags a pipe-less table header or a YAML line. `blocks(text)` (PARSE-7) says
   which lines are `table` or `code`; those lines are never rewritten. A `#` inside a
   fenced code block would be ignored by `MarkdownNodeParser` anyway, but a `#` inside a
   table row would break the table.
3. **Deterministic and reproducible.** Same clean file, same markdown file; the manifest
   records its sha256, so the copy can be deleted and rebuilt at any time.

Real example, the scheduler page (bare labels, 143 lines, 20 headings):
```
clean line 2   Overview:              →   markdown line 2   ## Overview:
clean line 6   Audience:              →   markdown line 6   ## Audience:
clean line 0   Scheduler Health…      →   markdown line 0   # Scheduler Health…
```
The autotune playbook (underlined, 144 lines, 20 headings):
```
clean line 2   Summary                →   markdown line 2   ## Summary
clean line 3   ---                    →   markdown line 3   (empty)
```
Measured with the prototype: scheduler 20 sections, privilege manual 20, autotune 20,
ADR 6, every node's line range recovered.

Module: `pipeline/markdown_view.py`. Pure. File writing lives in PARSE-8b.

### 1. PARSE-8a  markdown_view  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** `markdown_view(text, headings, blocks)` to return the clean text with `#`s written on every heading line
**So that** LlamaIndex's `MarkdownNodeParser` sees the same sections our detector found, on every page style

**Acceptance Criteria (Gherkin)**
- Given `"Overview:\n\ntext"` and `[Heading(0, 2, "Overview:")]`, Then `"## Overview:\n\ntext"`
- Given `"Summary\n---\ntext"` and `[Heading(0, 2, "Summary")]`, Then `"## Summary\n\ntext"` (the underline line is emptied, not removed)
- Given `"# Title\n"` already Markdown and `[Heading(0, 1, "Title")]`, Then unchanged (no double `#`)
- Given a heading at a line that `blocks` marks as `table` or `code`, Then that line is unchanged
- Given any input, Then the output has exactly the same number of lines as the input
- Given every clean file, Then `MarkdownNodeParser` on the output yields as many sections as the detector found headings with a body, ±0, and the result fingerprints to `tests/golden/markdown_view_fingerprint.json`

**Example with real data**
Scheduler page: 20 heading lines rewritten, 123 lines untouched, 143 lines out. Autotune playbook: 20 headings rewritten, 20 underlines emptied, 144 lines out.

**Non-functional Requirements**
- Shared NFRs. Pure; no I/O. About 20 lines. Level 1 → `#`, level 2 → `##`, level n → n hashes.

**Dependencies**
- APIs: `markdown_view(text: str, headings: list[Heading], blocks: list[Block]) -> str`
- Uses: PARSE-5a `Heading`, PARSE-7a `Block`
- Service Bus: N/A · Database: N/A · UI: N/A

### 2. PARSE-8b  Markdown copy and manifest columns  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** the corpus writer to save `data/confluence/markdown/<same name>.md` for every clean file and add `md_sha256` and `rewritten_lines` to each manifest row
**So that** anyone can open the exact file that was chunked, diff it against clean, and prove only heading lines differ

**Acceptance Criteria (Gherkin)**
- Given a clean file, When the writer runs, Then `data/confluence/markdown/<name>.md` exists with the same line count
- Given the manifest row for that file, Then it has `md_sha256` (sha256 of the markdown bytes) and `rewritten_lines` (count of lines that differ from clean)
- Given a run over the corpus twice, Then every `md_sha256` is identical between runs
- Given the existing manifest columns and the clean-folder golden fingerprint, Then they are unchanged (clean files are not touched)
- Given a file with no headings, Then `rewritten_lines` is 0 and the markdown file equals the clean file

**Example with real data**
Manifest row for the scheduler page gains `"md_sha256": "…", "rewritten_lines": 20`. Autotune playbook: `"rewritten_lines": 40` (20 headings + 20 underlines).

**Non-functional Requirements**
- Shared NFRs. One pass over the corpus, under 30 s. The markdown folder is derived data: gitignored, rebuildable, never edited by hand.

**Dependencies**
- APIs: `write_markdown(clean_dir: Path, markdown_dir: Path, manifest: Path) -> None`, in the corpus writer next to PARSE-2's functions
- Uses: PARSE-2, PARSE-6, PARSE-7, PARSE-8a
- Service Bus: N/A · Database: N/A · UI: N/A

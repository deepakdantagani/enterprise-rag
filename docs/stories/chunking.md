# Chunking stories

The chunker, PARSE-8: `Heading` and `Block` lists in, `Chunk` values out. Design: [chunker design](../design/chunker-system-design.md).

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

---

## PARSE-8  Chunker  (split into one function per PR)

**Background for all of PARSE-8**
Everything so far produces two lists for a file: `blocks(text)` (what must stay whole)
and `detector_for(text).find_headings(lines)` (where sections start). The chunker turns
those into chunks: line ranges that never cross a heading, never cut a block, and pack
up to `max_chars` (2,048, about 512 tokens; PARSE-9 swaps the measure for the embedder's
tokenizer). No LlamaIndex here; PARSE-9 wraps it. The reasoning behind every number and
rule is in the [chunker design](../design/chunker-system-design.md); this background is the
short form.

The rules, in the order the code applies them:

1. **Heading lines are not content.** A block of kind `heading` is dropped. A `text` or
   `list` block whose first lines are headings loses those lines (a bucket C paragraph
   often starts with a label, e.g. `FAQ` / `Q: ...` stacked). A block left with no
   non-blank line is dropped.
2. **The block wins inside tables, code, quotes.** A heading line that falls inside a
   `table`, `code`, `quote`, `rule` or `html` block, or after content inside any block,
   is not honoured: it stays content and does not cut. (The label rule cannot see block
   structure; e.g. it flags a pipe-less table header row. 58 + 73 cases in the corpus.)
3. **A heading cuts.** Every honoured heading starts a new section; no chunk spans one.
4. **Pack, never split.** Blocks in the same section are packed greedily until the next
   block would push the chunk over `max_chars`. Size of a block = sum of `len(line) + 1`
   over its lines. A block bigger than `max_chars` goes through rule 6 first.
   - **4b. A lead-in sticks to what follows.** A one-line block immediately followed by
     a list is never the last block of a chunk; it moves to the next chunk with its
     list. (Runbooks write `8) Pin a model version` and then `-` bullets at column 0;
     markdown-it makes them two blocks, and the naive packer cut between them.)
5. **Breadcrumb from levels.** Each chunk carries `heading_path`, the stack of heading
   texts above it: push the heading, popping any heading of equal or deeper level first.
   Level 1 is the title, so the path always starts with it.
6. **Oversized blocks split by shape.** A `list` bigger than `max_chars` is split at
   top-level item boundaries only, so nested bullets stay with their step; a `table` is
   split at row boundaries and every piece repeats the header row and separator. `code`,
   `text` and `quote` are never split; they become a chunk on their own. At 2,048 chars
   the corpus has 271 such blocks: 221 lists, 34 tables, 9 paragraphs, 7 code fences,
   largest 10,722 chars.
7. **Never merge; carry the parent.** Each chunk records `section_line` (the honoured
   heading it sits under) and `parent_line` (that heading's parent, by level). PARSE-9
   turns those into ids and `PARENT`/`CHILD` relationships so retrieval can return a
   whole parent section when several of its children match. Sections are never merged
   at chunk time.

Where this differs from the archived v0 chunker (v0 fingerprint `570582ca…cb06`,
96,360 chunks, median 19 per file, median 479 chars, p95 1,453):

| Change | Why | Corpus impact |
|---|---|---|
| Headings at the start of a `list` block are honoured (rule 1) | v0 only split labels out of paragraphs, so a lone `3) Escalation` (a one-item list to markdown-it) never became a heading; the 4c rule was measured but never reached a chunk | 1,011 headings in 246 files |
| Stacked-label nesting moves into `LabelHeadings` (PARSE-12a) | v0 did it inside the chunker with a "native" flag on each heading; levels belong to the detector | same paths as v0 |
| `max_chars` 1,600 → 2,048 | 512 tokens is the industry default band and every hosted embedder accepts far more; 97% → 98% of sections fit whole | about 3,500 fewer split pieces |
| Oversized lists and tables are split (rule 6) | 221 of the oversized blocks are runbooks written as one numbered list where each step is the unit a question targets | 271 blocks, 0.3% of chunks |
| Lead-in sticks (rule 4b) | found by dry run on a PRD: a step title ended chunk 1 and its bullets started chunk 2 | every runbook with `N) title` + bullets |
| `section_line` / `parent_line` on every chunk (rule 7) | parent-child retrieval is the standard answer to "small chunks lack context"; the chunker's cost is two ints | none on chunk boundaries |

The PARSE-8e golden is generated from the new code after 8a–8d merge, and the story
records the exact diff against v0 (files identical, files changed, and why).

Real example, `dsid_0012a01f…scheduler-health-oracle…txt` (143 lines, 20 headings, 22 chunks in v0). First six:
```
Chunk(start=4,  end=5,  heading_path=['Scheduler Health Oracle and Self‑Heal Procedures', 'Overview:'],  block_kinds=['text'], section_line=2, parent_line=0)   441 chars
Chunk(start=7,  end=11, heading_path=[..., 'Audience:'],                                   block_kinds=['list'])   176 chars
Chunk(start=12, end=16, heading_path=[..., 'Why SHO: problem statement'],                  block_kinds=['list'])   457 chars
Chunk(start=17, end=23, heading_path=[..., 'High-level design'],                           block_kinds=['list'])   780 chars
Chunk(start=24, end=32, heading_path=[..., 'Detection signals and thresholds (baseline)'], block_kinds=['list'])   708 chars
Chunk(start=33, end=38, heading_path=[..., 'Policy mapping examples'],                     block_kinds=['list'])   674 chars
```
Line 2 `Overview:` and line 6 `Audience:` are headings, so they are in the path and not
in any chunk's lines. Chunk 7 (lines 39-53, 1,118 chars) packs three blocks, `list`,
`list`, `text`, under `Runbook: automated remediation decision flow`.

Module: `pipeline/chunker.py`. Pure. Chunk text is assembled in PARSE-9, not here.

### PARSE-8a  Chunk value and block_size  ⬜

**Status:** To do

**As a** RAG developer
**I want to** a `Chunk(start, end, heading_path, block_kinds, section_line, parent_line)` value and `block_size(lines, block)`
**So that** the output shape and the one size measure are fixed before any packing logic

**Acceptance Criteria (Gherkin)**
- Given `Chunk(start=7, end=11, heading_path=["T", "Audience:"], block_kinds=["list"], section_line=6, parent_line=0)`, When I read it, Then the fields come back; it is frozen and compared by value
- Given a file whose line 0 is not a heading, Then `section_line` and `parent_line` may be `None`
- Given lines `["ab", "", "cde"]` and `Block("text", 0, 3)`, When I call `block_size`, Then `3 + 1 + 4 = 8` (each line counts `len + 1` for its newline)
- Given a block of zero lines, Then `0`

**Example with real data**
The `Audience:` list, `Block("list", 7, 11)` in the scheduler file: `block_size` = 176, which is the 176 chars of chunk 2 above.

**Non-functional Requirements**
- Shared NFRs. Pure. `heading_path` is stored as a tuple so the value stays hashable.

**Dependencies**
- APIs: `Chunk(start: int, end: int, heading_path: tuple[str, ...], block_kinds: tuple[str, ...], section_line: int | None, parent_line: int | None)`; `block_size(lines: list[str], block: Block) -> int`
- Uses: PARSE-7a `Block`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8b  content_blocks  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `content_blocks(lines, blocks, headings)` to return the blocks with heading lines removed (rules 1 and 2)
**So that** the packer only ever sees content, and "which headings are honoured" falls out: a heading line that still lies inside a content block was not honoured

**Acceptance Criteria (Gherkin)**
- Given `Block("heading", 2, 3)`, Then it is dropped
- Given `Block("text", 4, 7)` and headings at lines 4 and 5 (stacked labels), Then `Block("text", 6, 7)`
- Given `Block("list", 9, 11)` (`3) Escalation` + blank) and a heading at 9, Then the block is dropped (no non-blank line left)
- Given `Block("table", 20, 24)` and a heading at 20, Then the block is returned unchanged (rule 2)
- Given `Block("list", 17, 26)` and a heading at 22 (after content), Then unchanged
- Given no headings, Then the blocks are returned unchanged (minus `heading` kinds)
- Given every clean file, Then no returned block overlaps another and every returned block has at least one non-blank line

**Example with real data**
Scheduler file: `Block("text", 2, 3)` (`Overview:`) is dropped, `Block("list", 7, 11)` (`Audience:` items) is returned unchanged because line 6, the heading, is its own one-line text block that gets dropped.

**Non-functional Requirements**
- Shared NFRs. Pure. Never mutates its inputs.

**Dependencies**
- APIs: `content_blocks(lines: list[str], blocks: list[Block], headings: list[Heading]) -> list[Block]`
- Uses: PARSE-7a, PARSE-5a
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8c  heading_paths  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `heading_paths(headings)` to give each heading its breadcrumb (rule 5)
**So that** the chunk's `heading_path` is one lookup, and the stack logic is testable on headings alone

**Acceptance Criteria (Gherkin)**
- Given `[Heading(0,1,"T"), Heading(2,2,"A"), Heading(8,2,"B")]`, Then `[("T",), ("T","A"), ("T","B")]`
- Given levels 1, 2, 3, 2, Then the level-3 heading's path has three entries and the last level-2 heading's path has two (the level 3 was popped)
- Given levels 1, 3 (a jump), Then `("T", "X")`: depth is by stack, not by level number
- Given `[]`, Then `[]`
- Given every clean file, Then every path starts with the title when line 0 is a heading

**Example with real data**
Scheduler file, heading 2 `Overview:` (level 2) -> `('Scheduler Health Oracle and Self‑Heal Procedures', 'Overview:')`. A bucket A file with `## Scope` then `### Details`: `('Title', 'Scope', 'Details')`.

**Non-functional Requirements**
- Shared NFRs. Pure.

**Dependencies**
- APIs: `heading_paths(headings: list[Heading]) -> list[tuple[str, ...]]`, same length as the input
- Uses: PARSE-5a
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8d  pack  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `pack(lines, blocks, cuts, max_chars)` to group content blocks into runs (rules 3 and 4)
**So that** the packing rule is testable with hand-made blocks and a set of cut lines

**Acceptance Criteria (Gherkin)**
- Given three blocks of sizes 500, 500, 500 and `max_chars=2048`, no cuts, Then one run of three
- Given sizes 1100, 1100, Then two runs (the second would push over 2,048)
- Given sizes 1900, 30 (one line), 400 (a list), Then two runs and the 30-char lead-in is in the second run with its list (rule 4b)
- Given one block of size 5,000, Then one run of one; given 100 then 5,000 then 100, Then three runs
- Given blocks at lines 0-2 and 3-5 and a cut at line 3, Then two runs even though both fit
- Given `[]`, Then `[]`
- Given every fixture file, Then every content block is in exactly one run, runs are in order, no run contains a cut line strictly inside it, and no run ends with a one-line block that is followed by a list

**Example with real data**
Scheduler file, section `Runbook: automated remediation decision flow` (lines 39-53): blocks `list` (39-46), `list` (46-51), `text` (51-53) total 1,118 chars, so one run. The next heading at line 54 is a cut, so the run ends there.

**Non-functional Requirements**
- Shared NFRs. Pure. `cuts` is a set of line numbers (the honoured heading lines); a block starts a new run if any cut lies in `(previous block end - 1, block.start]`. Rule 4b: when a run would end on a one-line block whose next block is a `list`, that block opens the next run instead.

**Dependencies**
- APIs: `pack(lines: list[str], blocks: list[Block], cuts: set[int], max_chars: int) -> list[list[Block]]`
- Uses: PARSE-8a `block_size`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8e  chunk  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `chunk(lines, blocks, headings, max_chars=2048)` to compose 8b, 8f, 8g, 8c, 8h, 8d into `Chunk` values
**So that** PARSE-9 has one call to make

**Acceptance Criteria (Gherkin)**
- Given the scheduler file's lines, blocks and headings, When I call `chunk`, Then the first six chunks equal the listing in the PARSE-8 background
- Given headings at lines 2 and 8 and blocks in between, Then no chunk's `[start, end)` contains line 2 or 8
- Given a heading followed directly by another heading, Then the second one's path includes the first (via PARSE-12a levels)
- Given every fixture file and every clean file, Then every non-blank line is either an honoured heading line or inside exactly one chunk, and chunks are in line order
- Given every clean file, When I fingerprint `<file> <start> <end> <path>` per chunk, Then it equals `tests/golden/chunks_fingerprint.json` (generated once from this code; the story records the diff vs v0: files identical / changed and why); skipped if the data folder is missing

**Example with real data**
The PARSE-8 background listing. `block_kinds` is the sorted set of kinds in the run, e.g. `('list', 'text')` for chunk 7.

**Non-functional Requirements**
- Shared NFRs. Pure. About 20 lines: the composition only, no rule of its own. Order: content_blocks → split_oversized → pack → Chunk values with paths and parent lines.

**Dependencies**
- APIs: `chunk(lines: list[str], blocks: list[Block], headings: list[Heading], max_chars: int = 2048) -> list[Chunk]`
- Uses: PARSE-8a-h, PARSE-12a
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8f  split_list  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `split_list(lines, block, max_chars)` to cut an oversized `list` block at top-level item boundaries (rule 6)
**So that** a runbook written as one numbered list becomes one chunk per step, and a nested bullet never leaves its step

**Acceptance Criteria (Gherkin)**
- Given a `list` block of 2,618 chars with top-level items `1.`, `2.`, `3.` and nested `-` bullets under each, and `max_chars=2048`, Then three blocks, each starting at a top-level item line and containing its nested lines
- Given a `list` block that fits in `max_chars`, Then `[block]` unchanged
- Given a `list` block whose single top-level item is itself bigger than `max_chars`, Then `[block]` unchanged (never cut inside an item)
- Given top-level items of sizes 900, 900, 900 and `max_chars=2048`, Then two blocks: items 1-2 and item 3 (items are packed, not one per block)
- Given every oversized `list` block in the corpus (221 at 2,048), Then the pieces cover the block's lines exactly, in order, and every piece starts on a top-level item line

**Example with real data**
`dsid_ad85c50d…` line 29, a 36-line, 2,618-char list: `1. Detection and triage`, `2. Immediate containment`, `3. Controlled healing`, each with 3-4 nested bullets. Result: three blocks at the three numbered lines.

**Non-functional Requirements**
- Shared NFRs. Pure. A top-level item line is a line whose list marker starts at the block's own indent.

**Dependencies**
- APIs: `split_list(lines: list[str], block: Block, max_chars: int) -> list[Block]`
- Uses: PARSE-7a `Block`, PARSE-8a `block_size`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8g  split_table  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `split_table(lines, block, max_chars)` to cut an oversized `table` block at row boundaries, repeating the header on every piece (rule 6)
**So that** a value in row 40 still sits under its column names in the chunk that carries it

**Acceptance Criteria (Gherkin)**
- Given a `table` block of 60 rows, 4,000 chars, and `max_chars=2048`, Then two or more pieces; each piece after the first is a `TableSlice(block, header_lines=(h, sep), start, end)` so the chunk can render the header again without the lines existing twice in the file
- Given a `table` that fits, Then `[block]` unchanged
- Given a `table` whose header plus one row exceeds `max_chars`, Then one row per piece, never a cut inside a row
- Given every oversized `table` in the corpus (34 at 2,048), Then the pieces cover the body rows exactly, in order

**Example with real data**
The largest corpus table, `dsid_…` (to be named when the story is picked up): 58 rows, 5,100 chars, header `| Parameter | Description | Default |`. Result: three pieces, each with the header row and separator, rows 1-22, 23-44, 45-58.

**Non-functional Requirements**
- Shared NFRs. Pure. The repeated header is a reference to the header lines, not copied text: `Chunk.start/end` stay honest line ranges and PARSE-9 renders the header when it builds node text.

**Dependencies**
- APIs: `split_table(lines: list[str], block: Block, max_chars: int) -> list[Block | TableSlice]`
- Uses: PARSE-7a `Block`, PARSE-8a `block_size`
- Service Bus: N/A · Database: N/A · UI: N/A

### PARSE-8h  parent_lines  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `parent_lines(headings)` to give each heading the line of its parent heading (rule 7)
**So that** a chunk can name its parent section by line, and PARSE-9 can build parent nodes and `PARENT`/`CHILD` links without re-deriving levels

**Acceptance Criteria (Gherkin)**
- Given `[Heading(0,1,"T"), Heading(2,2,"A"), Heading(8,2,"B")]`, Then `[None, 0, 0]`
- Given levels 1, 2, 3, 2, Then the level-3 heading's parent is the first level-2 line, and the last level-2's parent is line 0
- Given levels 1, 3 (a jump), Then the level-3 heading's parent is line 0: parent is by stack, not by level arithmetic
- Given `[]`, Then `[]`
- Given every clean file, Then every non-title heading has a parent, and the parent's line is smaller than its own

**Example with real data**
Playbook file: `### A. Confirm you are targeting…` (level 3) → parent is the line of `## Preconditions / Setup checklist`; that heading's parent is line 0, the title.

**Non-functional Requirements**
- Shared NFRs. Pure. Same stack walk as PARSE-8c; the two functions may share a helper.

**Dependencies**
- APIs: `parent_lines(headings: list[Heading]) -> list[int | None]`, same length as the input
- Uses: PARSE-5a
- Service Bus: N/A · Database: N/A · UI: N/A

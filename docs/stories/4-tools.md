# Tooling stories

Triage gate, measurement and audit tools that live under `tools/`, outside `pipeline/`.

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

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

## PARSE-14  Assumption audit: every chunking assumption as a corpus count  ⬜

**Status:** To do

**Background**
The chunker design ([design doc](../design/2-chunker-system-design.md)) rests on assumptions
about the parser's output, and dry runs on single pages keep finding cases where the
parser breaks one: a label with the colon in the middle, a `#` about to be written inside a table row. Reading pages one at a time
finds these by luck. This story turns each assumption into a function that scans the
corpus and reports how often it fails, with examples, so the design is checked by
numbers and re-checked after every parser change.

**As a** pipeline developer
**I want to** `tools/audit.py` to print one row per assumption: name, failing files, share of corpus, three example files with line numbers
**So that** a parser change can be judged by which rows it moves, and no assumption in the design is unmeasured

**Acceptance Criteria (Gherkin)**
- Given the clean corpus, When I run `uv run python tools/audit.py`, Then I get a table with at least these rows, each a pure function `audit_<name>(text) -> list[Finding]` in `tools/audits/`:
  - `mid_colon_label`: a line `Xxx: Yyy` directly followed by a list or numbered block and not a heading in the markdown copy
  - `false_heading`: a `##` written by the label rule that looks like code, YAML or a table row (`=`, `|`, `key: value` with lowercase key)
  - `heading_in_protected`: a label-shaped line inside a fence or table (must be 0 headings written there)
  - `heading_only_section`: a heading with no body (design: 11,343 today)
  - `section_over_budget`: sections over 512 tokens, the population `SentenceSplitter` windows (design: 1,698 at 2,048 chars)
  - `md_line_count`: markdown copy line count ≠ clean line count (must be 0)
  - `md_sections`: `MarkdownNodeParser` section count on the copy ≠ headings with a body (must be 0)
  - `colon_section`: a section whose body ends with `:` and has no list, table or code (design: 133)
- Given a row, When I read it, Then the count matches the number quoted in the design doc for that assumption on the current parser, or the design doc is updated in the same PR
- Given `pipeline/`, When I grep for `audit`, Then there are no matches (tools only)
- Given `--json`, Then the same table as JSON, so a later story can diff two runs

**Example with real data**
`mid_colon_label` on `…privilege-approval-safeguards…` line 77: `Operational Runbook: Approving a Level 3 Grant (step-by-step)` followed by `1)`.

**Non-functional Requirements**
- Shared NFRs. Each audit is one pure function over one file's text, about 15 lines, with doctests; the runner only loops and prints. Full corpus under 60 s.
- Every new assumption added to the design doc gets an audit row in the same PR.

**Dependencies**
- Uses: PARSE-8b, PARSE-8c, PARSE-9a
- Service Bus: N/A · Database: N/A · UI: N/A

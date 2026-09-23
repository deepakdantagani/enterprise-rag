# Linear stories

The Linear source of EnterpriseRAG-Bench: 35,308 ticket exports, from raw bytes to LlamaIndex nodes.
Shared rules, the story template and the Confluence glossary are in [stories.md](../stories.md); every story here
follows them. The design these stories implement is [3-linear-system-design.md](../design/3-linear-system-design.md),
and each story names the requirement (F1–F14, N1–N10) it satisfies.

**Glossary for this file** (a story should make sense without chat history):

- **Ticket**: one Linear issue exported as `.txt` under `data/linear/raw/linear/`. 35,308 files, 182 MB.
- **dsid**: the 32-hex id at the front of every filename, e.g. `dsid_000091d8da3a4642a3c5acd442676e48`.
  It is what `questions.jsonl` lists in `expected_doc_ids`, so it is **the key the benchmark scores**.
  It is also the only unique key: 5,060 `TEAM-number` ticket keys are shared by more than one file.
- **Activity entry**: a dated line in a ticket recording an update, e.g.
  `2025-12-05 (Marcus Lin): Security note: payload must not include prompt text`.
  208,691 of them across 33,260 files (94.2%), in seven written shapes. They are the ticket's history.
- **Narrative**: every non-blank line that is not an activity entry — the description, goals,
  acceptance criteria, rollout plan. 83.4% of non-blank lines.
- **Bare label line**: a section header written with no markup, e.g. `Background`, `Open questions`.
  10,365 Linear files use them; `pipeline/label_rule.py` (built for Confluence) already detects them.
- **Truth set**: real files with every line hand-labelled `activity` or `narrative`, used to test
  the classifier. Same idea as PARSE-17 did for Confluence headings.
- **Golden fingerprint**: one sha256 over every file's output sha256, in manifest order. If a refactor
  changes one byte anywhere in the corpus, the test fails.
- **`_stats.json`**: the counts of one stage's run (files read, entries by shape, nodes by type),
  written next to that stage's `_manifest.json`. The manifest says what happened to each file;
  the stats file says what happened to the corpus. Built in LINEAR-9.
- **Dispatcher**: LlamaIndex's event bus (`llama_index.core.instrumentation`). Our code announces
  "a ticket was cleaned" / "a node was built"; a handler adds the announcements up into `_stats.json`.
  Already a dependency, so nothing new is installed.

**Shared non-functional requirements** (apply to every story in this file, on top of the ones in
[stories.md](../stories.md)):

- Deterministic: same input, same output, no network, no model call, no clock, no randomness (N1).
- Lossless: no story drops, truncates, summarizes, lowercases or de-punctuates corpus text (F2, N5).
  43% of the benchmark's gold answer facts contain a number and 14% a snake_case identifier;
  the "noise" is the answer.
- Behaviour-preserving: after the story, `uv run python -m unittest discover tests` is green and
  every existing golden fingerprint is unchanged (N2).
- Readable: top-of-file story, one idea per function, input → output doctests, early returns (N9).
- Maintainable: a rule true for more than one source lives in one shared module, never once per
  source (N11). Before writing a function, check whether `pipeline/` already has it — three of the
  stories below shrank or disappeared when someone did. Shared modules never import a source
  package, and a source package never imports another source's (N12).
- Observable: every stage emits typed events through the one LlamaIndex dispatcher, and the totals
  land in `_stats.json` next to that stage's manifest (N13). Counts only: an event's `timestamp` and
  `id_` are non-deterministic and must never reach a stats file, a manifest, a node id or a golden
  (N14).

**Order.** LINEAR-1a (the package split) comes first: it is a pure move, and everything else lands
inside the new layout. LINEAR-1b (the escape audit) and LINEAR-2 and LINEAR-3 can run in parallel
with it, since none of them changes pipeline code. Then LINEAR-1c needs 1a and 1b; LINEAR-4 needs
the truth set from 3; LINEAR-5 needs nothing new; LINEAR-9 needs 1a; LINEAR-6 needs 2, 4 and 5;
LINEAR-7 needs 1c and 2; LINEAR-8 needs 6, 7 and 9.

```
1a split ──┬── 1c normalize ── 7 corpus writer ──┐
1b audit ──┘                                     ├── 8 goldens
2 filename ─────────────────┐                    │
3 truth set ── 4 activity ──┼── 6a pack ── 6b nodes ──┘
5 sections ─────────────────┘
1a ── 9 counts ──────────────────────────────────┘
```

---

## LINEAR-1  Shared cleaning  (split into one function per PR)

Adding a second source is what forces the package boundary, so the split comes first and
everything else is built inside it. Measured basis for reusing rather than rewriting:
running the existing `pipeline/cleaning.clean_text` over all 35,308 Linear files, its
`fix_structure` step alters **0 files and 0 lines**. Confluence's cleaner is already
correct for Linear; only 4 nbsp and 3 zero-width files survive it untouched.

### LINEAR-1a  Split `pipeline/` by source  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** move the source-specific modules into `pipeline/confluence/` and create `pipeline/linear/`, changing no behaviour
**So that** a second source can be added without either source's rules leaking into the other

**Background**
`pipeline/` today is flat and every module in it is Confluence's, but three of them are
not Confluence-specific at all: `manifest.py` and `corpus.py` handle any source's files,
and `label_rule.py` finds bare-label headings that 10,365 Linear files also use. Leaving
the layout flat means the next six sources each guess what they may import.

The split is a **move with no logic change**, so every existing test and every Confluence
golden must pass untouched. If a golden moves, the PR is wrong.

| after the split | holds |
|---|---|
| `pipeline/normalize.py` | shared: unescape + whitespace (extracted in LINEAR-1c) |
| `pipeline/label_rule.py` · `manifest.py` · `corpus.py` | shared, already generic, unmoved |
| `pipeline/observability.py` | shared, added in LINEAR-9 |
| `pipeline/confluence/` | `cleaning.py` (wiki markup, table repair), `structure.py`, `to_markdown.py`, `buckets.py`, `headings.py`, `blocks.py` |
| `pipeline/linear/` | `filename.py`, `activity.py`, `sections.py`, `nodes.py` |

**Acceptance Criteria (Gherkin)**
- Given the move, When I run `uv run python -m unittest discover tests`, Then all 202 tests pass with no change to any test's expected values
- Given the Confluence goldens, Then `corpus_fingerprint.json` and every other golden file is byte-identical
- Given `pipeline/normalize.py`, `label_rule.py`, `manifest.py` or `corpus.py`, When I read their imports, Then none imports `pipeline.confluence` or `pipeline.linear`
- Given `pipeline/confluence/`, Then it imports no `pipeline.linear` module, and vice versa
- Given the PR diff, Then it contains only moved lines and changed import paths — no changed logic

**Example with real data**
`clean_text` over all 35,308 Linear files: `fix_structure` alters 0 files, 0 lines. That
measurement is why `cleaning.py` is reused for Linear and not reimplemented (N11).

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N11 (no duplicated rule) and N12 (explicit source boundary).
- Behaviour-preserving in the strongest sense: a pure move. Any behaviour change belongs in a different PR.

**Dependencies**
- APIs: import paths only
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: N11, N12

### LINEAR-1b  Escape audit: decide what the 213 files are  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** hand-inspect every Linear file that contains a literal `\n` but is not flagged as escaped, and record what each one actually is
**So that** the unescaping rule is changed on evidence, not on a guess that damages code samples

**Background**
805 Linear files contain a literal `\n`. The existing `is_escaped` — literal count
greater than real count, minimum 5 — flags only **592**. The 213-file gap is not one
thing; a first scan suggests three:

1. **Partly escaped bodies.** `dsid_…__DES-246891…`: `Summary:\nDesign pass for the
   compact rollout status component…`, 30 literal against 31 real newlines. The rule says
   no; the file plainly wants unescaping.
2. **Escaping inside an embedded code sample.** `dsid_…__PM-505021…`:
   `Python paginator example:\nfrom redwood import Client\nclient = Client()\n…`,
   42 literal against 69 real. Unescaping turns it into a readable code block — probably
   right, but it is a judgement call about code, not prose.
3. **A genuine printf or regex.** 68 files hold only one or two literal `\n`. Unescaping
   these would corrupt the example they are showing.

Getting this wrong is not cosmetic: leaving group 1 alone keeps ~174 files with their
whole body on one line, which is one oversized chunk and a badly diluted vector.

This story **decides nothing about the rule**. It produces the evidence; LINEAR-1c uses it.

**Acceptance Criteria (Gherkin)**
- Given the corpus, When I run the audit, Then it lists all 213 files with literal count, real count, and the first offending line
- Given each of the 213, When a human reads it, Then it is labelled `partly_escaped`, `code_sample` or `genuine_escape` and the labels are committed under `tests/fixtures/linear/escapes/`
- Given the labels, Then the audit reports how many files each candidate rule would unescape, and which labelled files each one gets wrong
- Given the same corpus, When the audit is run twice, Then the output is byte-identical
- Given the audit, Then it changes no pipeline code and no golden

**Example with real data**
```
literal real  label            file
    30   31   partly_escaped   …__DES-246891-compact-rollout-contrast-and-microcopy-polish.txt
    42   69   code_sample      …__PM-505021-sdk-client-evolution-paginate-retry-streaming.txt
     1   58   genuine_escape   (68 files with 1–2 literal \n)
```

**Non-functional Requirements**
- Shared NFRs at the top of this file. The labels are data: committed, reviewed once, and
  changed only when a human decides a label was wrong — never to make a test pass.

**Dependencies**
- APIs: an audit script under `tools/`, outside `pipeline/`; labels under `tests/fixtures/linear/escapes/`
- Depends on: nothing
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: the evidence for LINEAR-1c; F1

### LINEAR-1c  `normalize_text`: the shared cleaner  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** extract the source-agnostic cleaning rules into `pipeline/normalize.py`, apply LINEAR-1b's verdict, and add the seven invisible-character files
**So that** all eight sources share one cleaner and Confluence keeps `fix_structure` to itself

**Background**
Today `clean_text` = unescape + `fix_structure` + `normalize`. After this story,
`normalize_text` = unescape + whitespace, and Confluence's `clean_text` = `normalize_text`
+ `fix_structure`. Confluence's output must not move by one byte.

It keeps the existing `CleanResult(text, was_escaped)` return type deliberately: that is
what `manifest_row` already takes, so the whole manifest path is reused with no new code
(N11).

Measured across the seven other sources' sample slices (6,465 files) plus all of Linear:
every source ships the same envelope and the same artifacts, and unescaping is the only
rule that is not cosmetic — median lines before → after, for files containing a literal
`\n`: Gmail 7 → 120, Fireflies 4 → 96, Google Drive 3 → 90, Linear 13 → 58.

Rule order is fixed: unescape → CR/CRLF to LF → invisibles → trailing whitespace →
collapse 3+ blank lines → final newline. Everything after unescape depends on real line
breaks existing. (`str.splitlines()` already handles CR and CRLF, so that step is free.)

**Acceptance Criteria (Gherkin)**
- Given every Confluence raw file, When I run the new `clean_text`, Then `corpus_fingerprint.json` is unchanged
- Given a body containing literal `\n` and `\"`, Then they become real newlines and quotes
- Given the files LINEAR-1b labelled `genuine_escape`, Then they are **not** unescaped
- Given the files LINEAR-1b labelled `partly_escaped`, Then they **are** unescaped
- Given nbsp or a zero-width character, Then it is normalized (4 and 3 Linear files)
- Given a URL, snake_case identifier, CAPS token, em dash or `@mention`, Then it is returned byte-identical
- Given `pipeline/normalize.py`, When I read it, Then it names no source, mentions no wiki markup, and reads or writes no file
- Given fixtures from Linear, Slack and Gmail, Then the same function cleans all three correctly

**Example with real data**  (`dsid_007f029aebc94c02b6807da04107314a__ENG-130998-tenant-traffic-governor…txt`)

Before — 8 lines, 5,674 bytes, body on one line with `\n` as two characters:
```
'Tenant traffic governor and granular fairness controller\n\nSummary:\\nImplement a runtime-integrated
Tenant Traffic Governor (TTG) and Granular Fairness Controller (GFC) for Dedicated capacity that…'
```
After — 57 lines, 5,627 bytes:
```
'Tenant traffic governor and granular fairness controller\n\nSummary:\nImplement a runtime-integrated
Tenant Traffic Governor (TTG) and Granular Fairness Controller (GFC) for Dedicated capacity that…'
```
805 Linear files contain a literal `\n`; 606 of the 6,465 files in the seven other
sources' sample slices do too (Gmail 316, GitHub 138, Jira 57, Slack 41, Google Drive 30,
Fireflies 24, HubSpot 0).

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N11 and N12: no Linear-specific rule in this
  module, proved by running its tests over fixtures from three different sources.

**Dependencies**
- APIs: `normalize_text(raw: str) -> CleanResult` in `pipeline/normalize.py`; `pipeline/confluence/cleaning.clean_text` becomes `normalize_text` + `fix_structure`
- Depends on: LINEAR-1a (the package exists), LINEAR-1b (the verdict)
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F1, F2, N3, N10, N11

---

## LINEAR-2  `parse_filename`: the id comes from the name  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** turn a ticket filename into its four parts
**So that** every node can carry the `dsid` the benchmark scores, plus the team and ticket key as filters

**Background**
Nothing inside a ticket says which ticket it is. There is no `URL:`, `Team:` or `Project:` field —
grepped all 35,308 files: `Assignee:`, `Cycle:` and `URL:` appear zero times, `Team:` and `Project:`
once each. The filename is the only source of identity.

`dsid` is the primary key. `ticket_key` is **not**: 5,060 `TEAM-number` keys appear under more than one
`dsid`, which is exactly why 4 of the benchmark's Linear questions are about contradicting documents.
One file in the corpus has no ticket key at all and must not crash the parser.

**Acceptance Criteria (Gherkin)**
- Given `dsid_000091d8da3a4642a3c5acd442676e48__ENG-3927-add-audit-log-events.txt`, When I call `parse_filename(name)`, Then I get `dsid='dsid_000091d8da3a4642a3c5acd442676e48'`, `team='ENG'`, `ticket_key='ENG-3927'`, `slug='add-audit-log-events'`
- Given `dsid_7955b78fe4b2404eb8baa873a38b3a07__suggestions-risk-badge-visual-exploration.txt`, Then `team=''` and `ticket_key=''` and `slug='suggestions-risk-badge-visual-exploration'`, and no exception is raised
- Given a name that does not start with `dsid_`, Then a `ValueError` names the file
- Given all 35,308 real filenames, When I parse each, Then 35,307 have a non-empty `ticket_key` and the teams are exactly ENG 23,168 · PM 8,703 · DES 3,436

**Example with real data**
```python
>>> parse_filename('dsid_000091d8da3a4642a3c5acd442676e48__ENG-3927-add-audit-log-events-for-gate-decisions-and-overrides.txt')
TicketName(dsid='dsid_000091d8da3a4642a3c5acd442676e48', team='ENG', ticket_key='ENG-3927',
           slug='add-audit-log-events-for-gate-decisions-and-overrides')
```

**Non-functional Requirements**
- Shared NFRs at the top of this file.

**Dependencies**
- APIs: `parse_filename(name: str) -> TicketName(dsid, team, ticket_key, slug)` in `pipeline/linear/filename.py`
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F4

---

## LINEAR-3  Activity truth set: real files with hand-labelled lines  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** a set of real tickets where every non-blank line is hand-marked `activity` or `narrative`
**So that** LINEAR-4 is written against decisions a human made, and its disagreements are listed and explained instead of quietly tuned away

**Background**
This is PARSE-17 for Linear, and it is written **before** the classifier, not after. The corpus makes
the classifier harder than it looks, and only hand-labelled lines will catch it:

- Seven written shapes (counts are lines, measured over the whole corpus):
  `date - author:` 103,823 · `date author:` 52,559 · `date:` with no author 39,724 ·
  `date | author:` 5,179 · `date (author):` 4,411 · `author (date):` 2,847 · `[date] author:` 148.
- 39,724 entries have **no author and a colon inside the text**:
  `2025-02-14: Chose hybrid scoring: exact-match (priority), then lexical similarity…`
- 2,847 entries put the **author first**: `Marta Ruiz (2026-03-12): Need final alt-text strings.`
- 11,088 dated lines name a role or an event rather than a person:
  `2026-03-11 - Security review requested…`. These are still activity; they carry decisions.
- Narrative lines can contain dates and colons too (`- 2026-01-18 21:00–23:00 UTC: runtime upgrade window`),
  so the rule cannot be "has a date".

**Acceptance Criteria (Gherkin)**
- Given 20 real ticket files copied under `tests/fixtures/linear/activity/`, When I read the truth file, Then every non-blank line of every file has a hand-decided label `activity` or `narrative`
- Given the 20 files, Then all seven shapes appear, and the author-less, author-first and role-named cases each appear at least 10 times
- Given the truth file, When I call `load_truth()`, Then I get `{filename: [(line_number, label), …]}`
- Given a classifier and the truth set, When I call `disagreements(classify)`, Then I get every line where the two differ, with the line text — so a story can quote them

**Example with real data**  (`…__ENG-3927-add-audit-log-events…txt`, lines 82–85)
```
 82  narrative   Open questions
 83  narrative   - Should rollout-controller also emit audit events for canary promotion blocked…
 84  activity    2025-12-02 (Michael Nguyen): Drafted event names + payload fields. Aligning with…
 85  activity    2025-12-05 (Marcus Lin): Security note: payload must not include prompt text, …
```

**Non-functional Requirements**
- Shared NFRs at the top of this file. The truth set is data, not code: it is committed, reviewed once,
  and changed only when a human decides a label was wrong — never to make a test pass.

**Dependencies**
- APIs: `load_truth() -> dict[str, list[tuple[int, str]]]`, `disagreements(classify) -> list[Disagreement]` in `tests/fixtures/linear/`
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: the SLO "activity classification agrees with the truth set ≥ 99%"

---

## LINEAR-4  `activity_entry`: judge every line on its own  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** `activity_entry(line)` to return the entry a line holds, or `None` if the line is narrative
**So that** a ticket's history is separable from its description without ever making a file-level decision

**Background**
The obvious design — "everything after the first dated line is the activity log" — is wrong for about
16,000 files. Only 52.5% of the 33,260 files with activity lines keep them as one uninterrupted block at
the end. In the other 47.5%, narrative resumes afterwards (p90 = 11 more narrative lines), because the
export flattened several ticket fields in whatever order it had them: a test plan or an action-item list
can follow the comment log. So this function looks at one line and nothing else, exactly as the
Confluence parser judges one line at a time for headings.

Two traps, both measured, both able to destroy tens of thousands of entries:
1. **Split on the first colon after the date, never the last and never any colon.** 39,724 author-less
   entries contain further colons in their text.
2. **Both orders exist.** 2,847 lines are `author (date):`, and a rule anchored on a leading date misses
   all of them; they cluster in DES files.

Author is `None` when the line has none. Author-less entries are kept, never dropped.

**Acceptance Criteria (Gherkin)**
- Given `'2025-02-10 10:22 - Aisha Patel: Kickoff note.'`, Then `Entry(date='2025-02-10', author='Aisha Patel', text='Kickoff note.')`
- Given `'2025-02-14: Chose hybrid scoring: exact-match (priority), then lexical similarity.'`, Then `author is None` and `text` is the whole sentence **including its inner colons**
- Given `'Marta Ruiz (2026-03-12): Need final alt-text strings.'`, Then `date='2026-03-12'` and `author='Marta Ruiz'`
- Given `'2026-03-11 - Security review requested by Legal.'`, Then it is an entry with `author='Security review requested by Legal'` or `None` — whichever the truth set says — and not narrative
- Given `'- Emit first-class Audit Log events for the lifecycle.'`, Then `None`
- Given `'- 2026-01-18 21:00–23:00 UTC: Dedicated runtime upgrade window'` (a dated **narrative** bullet), Then `None`
- Given the truth set from LINEAR-3, When I classify every line, Then agreement is ≥ 99% and every disagreement is listed in the PR description with a one-line reason
- Given the whole corpus, When I classify every non-blank line, Then 208,691 ± 1% are entries (16.6% of lines) across 33,260 ± 1% files
- Given the whole corpus, When the caller emits one `EntryClassified` per line, Then `_stats.json`'s `entries_by_shape` matches the seven counts above and its total equals `activity_entries`
- Given `pipeline/linear/activity.py`, When I read its imports, Then it imports no dispatcher and nothing that reads or writes files

**Example with real data**  (`…__ENG-3927…txt` line 84, and a `date:` line from `…__ENG-30521…txt` line 22)
```python
>>> activity_entry('2025-12-02 (Michael Nguyen): Drafted event names + payload fields.')
Entry(date='2025-12-02', author='Michael Nguyen', text='Drafted event names + payload fields.')

>>> activity_entry('2025-02-14: Chose hybrid scoring: exact-match (priority), then lexical similarity.')
Entry(date='2025-02-14', author=None, text='Chose hybrid scoring: exact-match (priority), then lexical similarity.')
```

**Non-functional Requirements**
- Shared NFRs at the top of this file.
- A corpus-wide count is committed as a golden number, so a later refactor that changes the rule by one
  line shows up as a changed count.

**Dependencies**
- APIs: `activity_entry(line: str) -> Entry | None` in `pipeline/linear/activity.py`
- Depends on: LINEAR-3 (the truth set must exist first)
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F6, F7

---

## LINEAR-5  `narrative_sections`: group the prose  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** group consecutive narrative lines into `(start_line, end_line)` sections
**So that** the description is cut at the author's own boundaries instead of at an arbitrary character count

**Background**
10,365 Linear files write their sections as bare label lines — `Background`, `Goal`,
`Non-goals / explicitly out of scope`, `Open questions` — with no `#` and no underline. This is exactly
the pattern `pipeline/label_rule.py` was written for on the Confluence corpus, and it is the one piece
of that work that transfers unchanged. Markdown headings barely exist here (394 files), so there is no
markdown-it stage in this pipeline.

Sections break at a blank line or at a bare label line. Activity lines are not this function's
business; it is handed only the narrative ones.

**Acceptance Criteria (Gherkin)**
- Given a ticket's narrative lines, When I call `narrative_sections(lines)`, Then I get line ranges that break at blank lines and at label lines
- Given a label line, Then it starts a new section and is the first line of it
- Given a ticket with no label lines and no blank lines, Then I get one section covering all of them
- Given the 10,365 files with label lines, Then every label line is the first line of a section
- Given the same input twice, Then the same ranges
- Given `pipeline/linear/sections.py`, When I read it, Then it calls the shared `label_rule` and contains no copy of its logic (N11)

**Example with real data**  (`…__ENG-3927…txt`, 91 lines, 9 label lines)
```
lines  3-5    Background
lines  7-26   Goal
lines 28-31   Non-goals / explicitly out of scope
lines 33-53   Requirements / Acceptance Criteria
lines 55-63   Implementation notes
lines 65-71   Testing / Verification
lines 73-75   Rollout plan
lines 77-80   Owner / Collaborators
lines 82-83   Open questions
```

**Non-functional Requirements**
- Shared NFRs at the top of this file.
- Reuses `pipeline/label_rule.py` unchanged. If it needs a change for Linear, that is a separate PR
  with its own Confluence golden check.

**Dependencies**
- APIs: `narrative_sections(lines: list[tuple[int, str]]) -> list[tuple[int, int]]` in `pipeline/linear/sections.py`
- Uses: existing `pipeline/label_rule.py`
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F8

---

## LINEAR-6  `to_nodes`: pack the ticket  (split into one function per PR)

### LINEAR-6a  `pack_runs`: narrative and activity never share a node  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** pack a ticket's classified lines into node-sized runs
**So that** a proposal and the comment that reversed it never end up in the same vector

**Background**
One embedding call returns one vector per node, not one per token. The narrative says what was
proposed; the activity log says what was decided months later, and 4 of the benchmark's Linear
questions are about exactly such contradictions. If both are in one node, one blurred vector has to
answer both, and neither matches well.

Three policies were simulated over all 35,308 files (4 chars per token):

| policy | nodes | per ticket p50 | tokens p10 / p50 / p95 | over 512 |
|---|---:|---:|---|---:|
| A one node per ticket | 35,308 | 1 | 876 / 1,254 / 1,916 | 35,243 |
| B one node per activity entry | 296,613 | 8 | 31 / 49 / 504 | 296 |
| **C narrative 512 + activity packed 400** | **124,879** | **3** | 130 / 383 / 509 | 296 |

C is the design. A exceeds every embedder budget. B is atomic but makes 208,691 vectors of median 49
tokens, dominated by generic project vocabulary, and multiplies the sibling nodes that retrieval must
later collapse back to one `dsid`.

**Acceptance Criteria (Gherkin)**
- Given consecutive narrative lines, When I pack them, Then each run is ≤ 512 tokens
- Given consecutive activity entries, Then each run is ≤ 400 tokens
- Given a run of one kind followed by the other kind, Then the current run always ends — the two kinds never share a node
- Given a single entry longer than 400 tokens, Then it is its own run and is **not** split
- Given a narrative section boundary from LINEAR-5, Then it ends the current run even if there is room left
- Given a run that fills the cap and one entry remains, Then that entry becomes a short trailing run, and the entry is still whole
- Given all 35,308 files, Then the total is 124,879 ± 1% runs and exactly 296 exceed 512 tokens
- Given the corpus run, Then `_stats.json` reports `nodes_built`, `nodes_by_type` and `nodes_over_512_tokens`, and `nodes_over_512_tokens` is 296

**Example with real data**  (`…__ENG-3927…txt`, 91 lines → 11 nodes)
```
 #  type       lines    tokens  first line
 1  narrative   3-5         80  Background
 2  narrative   7-26       233  Goal
 3  narrative  28-31        84  Non-goals / explicitly out of scope
 4  narrative  33-53       349  Requirements / Acceptance Criteria
 5  narrative  55-63       167  Implementation notes
 6  narrative  65-71        98  Testing / Verification
 7  narrative  73-75        63  Rollout plan
 8  narrative  77-80        38  Owner / Collaborators
 9  narrative  82-83        74  Open questions
10  activity   84-90       382  2025-12-02 (Michael Nguyen): Drafted event names + payload fields…
11  activity   91-91        42  2026-02-18 (Michael Nguyen): Shipped to limited prod cohort with…
```
Node 10 stops at 382 tokens because the next entry would cross 400, so node 11 is one short entry.
That is the rule working: an entry is never split, so a run may end short.

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N6 (≤ 512 tokens) and F14 (every non-blank line in exactly one run).

**Dependencies**
- APIs: `pack_runs(lines: list[Line], section_breaks: set[int]) -> list[Run]` in `pipeline/linear/nodes.py`
- Depends on: LINEAR-4, LINEAR-5
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F9, N6

### LINEAR-6b  `to_nodes`: metadata, ids and the oversized tail  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** turn runs into LlamaIndex `TextNode`s with stable ids and full metadata
**So that** every chunk can be traced to one `dsid` and an exact line range, and the same bytes always give the same id

**Background**
`dsid` on every node is not optional: `expected_doc_ids` in `questions.jsonl` is a list of dsids, so a
node that cannot name its dsid cannot be scored. The id scheme matches Confluence
(`sha256(clean_sha256 + ':' + start + ':' + end)`), so the same bytes and the same range give the same
id on every run; LlamaIndex's default is `uuid4()` and is passed over via `id_func`.

`date_start`, `date_end` and `authors` are filters, not embedded text. The vector sees the title plus
the node's own lines and nothing else.

296 runs still exceed 512 tokens — all single oversized narrative lines — and go through LlamaIndex's
`SentenceSplitter`. That is the only library call in this stage.

**Acceptance Criteria (Gherkin)**
- Given a run, When I build its node, Then metadata has `dsid`, `source='linear'`, `team`, `ticket_key`, `title`, `chunk_type`, `start_line`, `end_line`, `clean_sha256`
- Given an activity run, Then it also has `date_start`, `date_end` and `authors` (authors omitting the `None`s)
- Given a narrative run, Then it has none of those three keys
- Given the same file twice, Then identical node ids
- Given two files with the same `ticket_key` but different `dsid`, Then their nodes never collide
- Given a run over 512 tokens, Then `SentenceSplitter` splits it and each piece keeps the run's metadata and its own line range
- Given all 35,308 files, Then every non-blank clean line is in exactly one node, and no node exceeds 512 tokens

**Example with real data**  (node 10 from LINEAR-6a)
```json
{
  "id": "sha256(clean_sha256 + ':84:90')",
  "text": "Add audit log events for Optimize quality gate decisions and overrides\n\n2025-12-02 (Michael Nguyen): Drafted event names…",
  "metadata": {
    "dsid": "dsid_000091d8da3a4642a3c5acd442676e48",
    "source": "linear", "team": "ENG", "ticket_key": "ENG-3927",
    "title": "Add audit log events for Optimize quality gate decisions and overrides",
    "chunk_type": "activity", "start_line": 84, "end_line": 90,
    "clean_sha256": "…",
    "date_start": "2025-12-02", "date_end": "2026-02-10",
    "authors": ["Michael Nguyen", "Marcus Lin", "Jordan Lee", "Felix Schneider", "Sean Gallagher"]
  }
}
```

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N4 (traceable) and N5 (lossless).

**Dependencies**
- APIs: `to_nodes(clean_text: str, name: TicketName, clean_sha256: str) -> list[TextNode]`
- Depends on: LINEAR-2, LINEAR-6a; LlamaIndex `TextNode` and `SentenceSplitter`
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F10, F11, F13, F14, N4, N5

---

## LINEAR-7  Reuse the corpus writer for a second source  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** give the existing `write_clean_corpus` one parameter so it can clean any source, then run it for Linear
**So that** no second copy of the file-walking, manifest-writing code exists

**Background**
This story was originally two ("`normalize_one_file`", "`write_clean_corpus`") before
anyone read `pipeline/corpus.py`. It already does the job:

```python
def write_clean_corpus(raw_dir: Path, clean_dir: Path) -> list[dict]:
    for src in sorted(raw_dir.glob("*.txt")):
        raw = src.read_text(encoding="utf-8")
        result = clean_text(raw)                      # <- the only Confluence-specific line
        save_text(clean_dir / src.name, result.text)
        rows.append(manifest_row(src.name, raw, result))
```

`save_text`, `save_manifest`, `manifest_row` and `sha256` are already source-agnostic, and
`manifest_row` takes a `CleanResult` — which is exactly what LINEAR-1c's `normalize_text`
returns. So the entire story is: make `clean_text` a parameter defaulting to today's
value, and call it with `normalize_text` for Linear.

Two facts that make this safe. The Confluence golden hashes only `file` and
`clean_sha256`, so adding `dsid` and `source` keys to a row cannot break it. And rows are
already sorted by filename, so manifest order stays stable.

**Acceptance Criteria (Gherkin)**
- Given `write_clean_corpus(raw, clean)` called with no new argument, When I run the Confluence corpus, Then `corpus_fingerprint.json` is unchanged
- Given `write_clean_corpus(raw, clean, clean=normalize_text)`, When I run the Linear raw folder, Then `data/linear/clean/` holds 35,308 files with the same names
- Given the run, Then `_manifest.json` has one row per file with `file`, `dsid`, `source`, `raw_sha256`, `clean_sha256`, `raw_lines`, `clean_lines`, `raw_bytes`, `clean_bytes`
- Given `dsid`, Then it is derived from the filename by `parse_filename`, never re-derived from the text
- Given the writer runs twice, Then `_manifest.json` is byte-identical
- Given the run, Then exactly the number of files LINEAR-1b's verdict predicts are marked `was_escaped=True`
- Given the PR, Then no new file-walking or manifest-writing function is added

**Example with real data**
```json
{
  "file": "dsid_007f029aebc94c02b6807da04107314a__ENG-130998-tenant-traffic-governor-and-granular-fairness-controller.txt",
  "dsid": "dsid_007f029aebc94c02b6807da04107314a",
  "source": "linear",
  "raw_sha256": "f2aaab22a08d99db…", "clean_sha256": "0de6584cb10a907d…",
  "raw_lines": 8, "clean_lines": 57, "raw_bytes": 5674, "clean_bytes": 5627
}
```

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N7 (< 180 s for the corpus), N8 (streaming,
  < 500 MB RSS) and N11 (no duplicated rule — the point of this story).
- Emits one `TicketCleaned` event per file (LINEAR-9), from the writer, not from the pure function.

**Dependencies**
- APIs: `write_clean_corpus(raw_dir: Path, clean_dir: Path, clean: Callable = clean_text) -> list[dict]` — one new parameter on the existing function
- Depends on: LINEAR-1c, LINEAR-2
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: F3, N7, N8, N11

---

## LINEAR-8  Golden fingerprints for the Linear corpus  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** one sha256 over the clean corpus and one over the node list
**So that** any refactor that changes one byte of output fails a test instead of shipping

**Background**
Same mechanism as `tests/golden/corpus_fingerprint.json` for Confluence. Two files, because the two
stages fail for different reasons: cleaning damage is invisible until you diff bytes, and a chunking
change is invisible until you diff line ranges.

**Acceptance Criteria (Gherkin)**
- Given the clean corpus, Then `tests/golden/linear_corpus_fingerprint.json` holds one sha256 over every `clean_sha256` in manifest order
- Given the nodes, Then `tests/golden/linear_nodes_fingerprint.json` holds one sha256 over every node's `(id, dsid, chunk_type, start_line, end_line)` in file order
- Given `data/` is missing, Then both tests skip rather than fail (same rule as the Confluence goldens)
- Given a one-byte change anywhere in `normalize_text` or the packing rule, Then the matching test fails
- Given `_stats.json` from two consecutive runs, Then they are byte-identical, and neither contains a timestamp, an id or a duration (N14)

**Example with real data**
```json
{"files": 35308, "fingerprint": "…", "generated_from": "data/linear/clean/_manifest.json"}
{"nodes": 124879, "fingerprint": "…", "tokens_over_512": 296}
```

**Non-functional Requirements**
- Shared NFRs at the top of this file. A golden is never regenerated to make a test pass; it is
  regenerated only when a PR explains, in its description, which outputs changed and why.

**Dependencies**
- APIs: `tests/golden/linear_corpus_fingerprint.json`, `tests/golden/linear_nodes_fingerprint.json`
- Depends on: LINEAR-6b, LINEAR-7b
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: N1, N2

---

## LINEAR-9  Counts for every stage  ⬜

**Status:** To do

**As a** pipeline developer
**I want to** each stage to announce what it did, and one handler to write the totals as `_stats.json`
**So that** a rule change that halves the activity entries fails a test instead of shipping

**Background**
The pipeline reads 35,308 files and writes ~125,000 nodes. If a regex edit classified
40,000 activity lines instead of 208,691, nothing today would say so: the goldens would
fail, but only with "the fingerprint changed", and finding out *what* changed means
diffing thousands of files. A counts file answers it in one glance and gives the golden
something readable to assert.

This uses LlamaIndex's instrumentation module, already a dependency
(`llama-index-core==0.14.24`; the API below was run against that exact version). No new
dependency, no service, nothing leaves the process.

```python
# pipeline/observability.py
dispatcher = instrument.get_dispatcher("pipeline")

class TicketCleaned(BaseEvent):    was_escaped: bool = False
class EntryClassified(BaseEvent):  shape: str = ""      # 'date - author:' … or 'narrative'
class NodeBuilt(BaseEvent):        chunk_type: str = ""; tokens: int = 0

class StatsCollector(BaseEventHandler):
    """Adds events up. Counts only — never a timestamp, never an id."""
```

**Purity.** The pure functions do not import the dispatcher. `corpus.write_clean_corpus`
emits `TicketCleaned`, and the Linear node builder emits `EntryClassified` and
`NodeBuilt` — emission happens at the caller, so the existing "imports nothing that reads
or writes files" tests keep passing.

**The one hard rule.** `BaseEvent` carries a `timestamp` and an `id_`, and both change on
every run. Neither may reach `_stats.json`, a manifest, a node id or a golden.

**Not now: tracing.** Arize Phoenix and OpenTelemetry record step timings in a UI. That
answers "which step is slow" and "what did retrieval return" — query-time questions, and
timings cannot be asserted in a test. Ingestion is a 3-minute offline batch. The seam is
`dispatcher`: a Phoenix handler can be attached at the query stage later, changing nothing
in this pipeline.

**Acceptance Criteria (Gherkin)**
- Given a corpus run, When it finishes, Then `_stats.json` sits next to that stage's `_manifest.json`
- Given two runs of the same corpus, Then the two `_stats.json` files are byte-identical
- Given `_stats.json`, Then it contains no timestamp, no id and no duration — counts only
- Given the clean stage, Then `files_read` and `files_escaped` match the manifest exactly
- Given the node stage, Then `activity_entries`, `entries_by_shape`, `nodes_built` and `nodes_over_512_tokens` are present
- Given no handler is attached, Then the pipeline still runs and produces identical output
- Given `pipeline/normalize.py` or any `pipeline/linear/` pure function, When I read its imports, Then it does not import the dispatcher

**Example with real data**  (`data/linear/clean/_stats.json` after a full run)
```json
{
  "files_read": 35308,
  "files_escaped": 592,
  "activity_entries": 208691,
  "entries_by_shape": {
    "date - author:": 103823, "date author:": 52559, "date:": 39724,
    "date | author:": 5179, "date (author):": 4411, "author (date):": 2847, "[date] author:": 148
  },
  "nodes_built": 124879,
  "nodes_by_type": {"narrative": 89000, "activity": 35879},
  "nodes_over_512_tokens": 296
}
```
(The `nodes_by_type` split is the one number above that is an estimate, not yet measured.)

**Non-functional Requirements**
- Shared NFRs at the top of this file, plus N13 (observable) and N14 (observability never
  changes output).

**Dependencies**
- APIs: `pipeline/observability.py` — `dispatcher`, `TicketCleaned`, `EntryClassified`, `NodeBuilt`, `StatsCollector`; uses `llama_index.core.instrumentation`
- Depends on: LINEAR-1a (the shared package exists)
- Service Bus: N/A · Database: N/A · UI: N/A
- Satisfies: N13, N14

---

## Not in this file, and why

| Asked for by the generic Linear connector pattern | Why not here |
|---|---|
| GraphQL backfill, webhooks, reconciliation job | The input is a frozen benchmark export. There is no Linear API in this project. |
| `state`, `priority`, `labels`, `project_id`, `cycle_id` metadata | Do not exist in the export: grepped 35,308 files, `Assignee:`/`Cycle:`/`URL:` appear 0 times, `Team:`/`Project:` once each. |
| ACL principals, permission-aware retrieval | No ACL data, single-tenant benchmark, no leakage metric to score. |
| Comment quality filter ("+1", emoji, bot posts) | Nothing to filter: entries are median 23 words, only 1.6% under 10 words, no bot posts. It could only delete answer text. |
| LLM-generated issue summaries | Violates N1 (deterministic, no model calls) and risks paraphrasing away the identifiers 14% of gold answers need. |
| Cross-ticket project grouping inside Linear | All 9 `project_related` questions span *other sources* (Confluence, GitHub, Jira, Slack), never several Linear tickets. |
| Cross-source deduplication | Each source is graded independently; deduping would delete gold documents. |

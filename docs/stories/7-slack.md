# Slack stories

The Slack source of EnterpriseRAG-Bench, stage by stage. Rules and template:
[stories.md](../stories.md). Design and the measurements behind every number here:
[5-slack-system-design.md](../design/5-slack-system-design.md).

Slack-specific glossary (the shared one is in [stories.md](../stories.md)):

- **Thread**: one exported conversation, one `.txt` file under `data/slack/raw/`. 285,605 of them.
  Line 1 is the channel name; the rest are messages separated by a blank line.
- **Message**: one speaker's turn inside a thread. May span several lines and may contain a
  fenced code block with blank lines inside it.
- **Speaker line**: the prefix that opens a message, `Aisha (CS): ` or `build-bot: `. Name,
  optional role in brackets, colon, space.
- **dsid**: the document id in the filename, `dsid_<32 hex>__<unix_ts>-<slug>.txt`. Unique
  across all 285,605 files, so it is the id. The timestamp beside it is **not** a date: only
  73,578 distinct values cover the corpus, 1,063 files share `1765432100`, the years run from
  2001 to 2513, and the values are keyboard walks (`1923456789`). Do not treat it as a time,
  and do not rank on recency. There are no per-message timestamps anywhere in the corpus.
- **Chunk**: what goes to the embedder. One thread, unless the thread is over the token
  ceiling, in which case it splits on a message boundary. About 99% of threads are one chunk.
- **TextNode**: LlamaIndex's unit. Our chunks become these, and everything downstream of a
  node is library code — see section 8 of the design.

## Index

Clean, then parse, then embed. These stories are the low-level design: one function each, with
its contract, its Gherkin and a real-data example. The system design is
[5-slack-system-design.md](../design/5-slack-system-design.md).

**Every story below is also held to these four, on top of the shared list in
[stories.md](../stories.md):**

1. **Explicit criteria.** A story states its own maintainability bar in its Non-functional
   section — what stays pure, what may touch disk, what a later change must not break —
   rather than inheriting a generic line.
2. **Rules live in a table.** Cleaning and parsing rules are one named, documented table per
   module. Adding a rule is a row plus a test, not a new branch buried inside a function.
3. **Every rule carries its corpus count as a test.** `unescape` fires on 8,334 files;
   `indented_speaker` on 27,225. If a refactor moves a count, a test fails and says by how
   much. A rule with no measured count is a rule nobody has justified.
4. **Dependency discipline.** A story that wants a third-party dependency has to say which
   LlamaIndex component it rejected and why (NFR-7). So far none has needed one.

| Story | Status |
|---|---|
| SLACK-0  Corpus profile | ✅ |
| SLACK-1  `unescape` | ✅ |
| SLACK-2  `normalize_whitespace` | ⬜ |
| SLACK-3  events and a handler  *(shared, lands on master)* | ⬜ |
| SLACK-4  `write_clean_corpus` + manifest | ⬜ |
| SLACK-5  `channel_of` | ⬜ |
| SLACK-6  `split_messages` | ⬜ |
| SLACK-7  `parse_speaker` | ⬜ |
| SLACK-8  `parse_thread` + truth set | ⬜ |
| SLACK-9  `chunk_thread` | ⬜ |
| SLACK-10  `to_text_node` | ⬜ |
| SLACK-11  Embed + BM25 hybrid index | ⬜ |
| SLACK-12  recall@20 on the benchmark questions | ⬜ |

---

## SLACK-0  Corpus profile ✅

**Status** Done
**As a** engineer about to write a parser for 285,605 files
**I want to** a single `profile.json` with the counts every later story argues from
**So that** no story quotes a number nobody can reproduce

`tools/slack_profile.py`. It only counts: it changes no file and decides no rule. The file is
written to `data/slack/profile.json`, which is gitignored like every other generated corpus
file; the numbers that matter are pinned as a test instead (`test_real_corpus_counts`).

### Acceptance Criteria

```gherkin
Scenario: profile the whole corpus
  Given the 58 zip slices under data/slack/archives/
  When I run profile(archives_dir, out_path)
  Then profile.json holds files, bytes, token percentiles (4 chars per token, nearest rank),
       every channel-shaped word found on line 1 with its file count,
       and the count of files whose line 1 is not channel-shaped
  And the run reads the zips directly without extracting 964 MB to disk
  And re-running it produces a byte-identical file
```

**Line 1 is listed, not judged.** 130 distinct channel-shaped words appear on line 1: 36 on
3 or more files, and 94 on exactly one file. Of those 94, 62 are identical to the file's own
slug and 6 nearly so, so they are most likely topic names rather than channels, but a
one-thread channel is possible. Which words count as channels is SLACK-5's decision; this
profile is its evidence.

### Example with real data

```json
{ "files": 285605, "bytes": 964465933,
  "tokens": { "p50": 813, "p90": 1241, "p99": 1713, "max": 4370 },
  "line1_channel_shaped": { "incidents": 24044, "eng-platform": 23184, "...": 0,
                            "hysteresis-v0": 1 },
  "line1_other": 11992 }
```

These replace the design doc's slice-1 estimates (p99 1,725, max 3,101) and its
`11,827` files without a channel, which did not add up with its own 273,519.

### Non-functional Requirements

Shared list. Reads from the zips; extracting the corpus is not required by any story.
Runs in about 4 seconds on a laptop.

### Dependencies

APIs data contracts: none · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-1  `unescape(text) -> UnescapeResult` ✅

**Status** Done
**As a** parser that must not meet the two characters `\` and `n` where a line break belongs
**I want to** the 8,334 JSON-escaped threads turned back into real characters
**So that** message splitting sees real line breaks in every file

`pipeline/slack/unescape.py`. Pure: text in, `UnescapeResult(text, rules_fired)` out. It
imports nothing from the Confluence pipeline: `pipeline/cleaning.py` gates on a different
rule and has no `\r`, and each source keeps its own pipeline.

**Only escaped files are touched.** 17,971 files hold a literal `\n`, but only 8,334 were
saved as a JSON string: after line 1 and the blank line, the whole body is one line. In the
other 9,637 the `\n` means itself, mostly inside code (an SSE capture `data: {...}\n\n`, a
`printf`), and a blanket replace would change that code. `is_escaped` is the gate: the body
after the first blank line, ignoring a final newline, is one line and holds a literal `\n`
that is not the tail of an escaped backslash (`C:\\new` is a path, not a line break), so a
second run never changes a thread again.

| rule considered | files | verdict |
|---|---|---|
| body on one line (chosen) | 8,334 | simple; catches short escaped threads too |
| Confluence count rule (5+ literal, more literal than real) | 8,479 | misses 4 short escaped threads |
| either rule | 8,483 | adds 149 escaped threads with a real code block; two rules to test |
| every file with a literal `\n` | 17,971 | corrupts code in ~9,490 normal files |

**The escapes are JSON's, decoded once, left to right.** The `ESCAPES` table has `\n` `\"`
`\t` `\r` `\\` `\/`, plus `\uXXXX`. (`\b` and `\f` are left out: they would put control characters
into chat text.) One regex pass means `C:\\new` becomes `C:\new`, not `C:\`, a
line break and `ew`. A surrogate pair (`\ud83d\ude00`) becomes one emoji; a lone surrogate
stays as written, so the output is always valid UTF-8. An unknown escape (`\s` in a regex)
stays. Two threads are escaped twice; they are decoded once, like everything else.

**No library does this.** On the 8,334 files, `json.loads` crashes on 4,317 (4,254 also hold a
bare `"`, which ends a JSON string) and agrees with this code on 4,010 of the 4,017 it can
read. `codecs.decode(..., "unicode_escape")` reads text as Latin-1 and matches on 2,021.

**Handed on to SLACK-6:** in 2,016 escaped threads each message ends in one `\n`, not a blank
line, so after unescaping they have line breaks but no blank line between messages.

### Acceptance Criteria

```gherkin
Scenario: an escaped thread becomes a real one
  Given a thread whose body is one line holding the two characters \n between messages
  When I unescape it
  Then those become real line breaks and rules_fired counts them

Scenario: an escaped quote, tab, carriage return, backslash or unicode escape
  Given \" \t \r \\ or \u2014 inside an escaped thread
  Then each becomes its real character, and \\n becomes a backslash and an n

Scenario: a thread that is not escaped is untouched
  Given a multi-line thread, even one with \n or \" inside a code block
  Then unescape returns it byte for byte with rules_fired {}

Scenario: running it twice changes nothing more
  Given the output of unescape
  Then unescape returns it unchanged
```

### Example with real data

Before, `dsid_919525fd...__1814012345-morning-riddle-and-wfh-poll.txt` (1,324 bytes, 2 real
line breaks, the body on one line):

```text
general

Lena: Morning riddle: ... Guess! :coffee:\nCarlos: 5am brewer? lie. ...\nLena: Poll: WFH Friday next week? ```/poll \"WFH Friday\" \"Yes\" ...```\n...
```

After: `rules_fired = {"newline": 17, "quote": 8}`, 19 real line breaks, one message per line,
`/poll "WFH Friday" "Yes" ...`.

The earlier example here, `dsid_0161f905...cred-cleanup-rotation-playbook-checkin.txt`, is not
escaped: 0 literal `\n`, 78 real line breaks. Its 14 `\"` are inside shell commands in a code
block, and unescape leaves them alone.

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** the escapes are the `ESCAPES` table; a new escape is a row. `\uXXXX` is the
  one pattern outside it, because it has 65,536 forms.
- **Pure:** no disk, no dispatcher call. The caller (SLACK-4) emits the event from
  `rules_fired`.
- **Corpus counts as tests** (`test_files_each_rule_fires_on`): 8,334 files changed; per rule,
  files where it fired: newline 8,334, quote 4,083, backslash 787, unicode 147, tab 36,
  carriage_return 19, slash 14. The 17,232 files with `\"` and the 243 with `\t` are corpus-wide counts;
  most of them are not escaped files.

### Dependencies

APIs data contracts: none · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-2  `normalize_whitespace(text) -> str` ⬜

**Status** To do
**As a** speaker parser that anchors on the start of a line
**I want to** the 27,225 threads with an indented speaker line straightened out
**So that** ` tom_ae: FYI ...` parses as a message rather than as body text

The trap: 27,057 threads (9.47%) contain **legitimate** indentation — list items and fenced
code. A blanket strip of leading whitespace destroys them. Only a line that is otherwise a
speaker line may lose its indent.

### Acceptance Criteria

```gherkin
Scenario: an indented speaker line is straightened
  Given the line " tom_ae: FYI customer claims integrations built during POC..."
  Then it becomes "tom_ae: FYI customer claims integrations built during POC..."

Scenario: an indented list item is left alone
  Given the line "  - Verify SOC2 Type II (owner: Ben)"
  Then it is unchanged

Scenario: indentation inside a fenced code block is left alone
  Given an indented line between two ``` fences
  Then it is unchanged, whatever it looks like

Scenario: the remaining whitespace rules
  Given trailing spaces, a CR, a non-breaking space, or 3+ consecutive blank lines
  Then trailing whitespace goes, CR goes, nbsp becomes a space, blank runs collapse to one
  And the file ends with exactly one newline
```

### Example with real data

Before, from a `sales` thread:

```text
jen_sales: Quick sync - ACME PoC is greenlighted but procurement raised 3 blocking items...
 tom_ae: FYI customer claims integrations built during POC must remain theirs.
 sana_se: I reviewed the deliverables - POC outputs are config + prompt recipes.
```

After: three messages, none of them indented.

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** one rule table, each row a name, a matcher and a fix, applied in a stated
  order. The order is part of the contract: the fence guard runs before anything that touches
  leading whitespace, or the code rules corrupt code blocks.
- **Pure:** no disk, no dispatcher call. Returns text plus the rules that fired.
- **Corpus counts as tests:** 237,002 files (82.98%) have no final newline, 64,212 (22.48%)
  trailing whitespace, 27,225 (9.53%) an indented speaker line, 448 (0.16%) 3+ consecutive
  blank lines, 250 a CR, 47 a non-breaking space. And the guard rail: 27,057 files (9.47%)
  have legitimate indentation and must come through untouched.

### Dependencies

APIs data contracts: SLACK-1 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-3  `pipeline/observability.py`: events and a handler ⬜  *(shared — lands on master first)*

**Status** To do
**As a** person about to run a pipeline over 285,605 files on a laptop
**I want to** every stage to say what it did, through LlamaIndex's own instrumentation
**So that** a run that stalls, skips or errors can be diagnosed without rerunning it under a debugger

**This story is not Slack-specific, and is not built in this branch.** Gmail and Linear have
their own worktrees and the same need, so three branches would otherwise each write it and
collide. It lands on master as its own small PR, and the source branches rebase onto it. The
events therefore carry a `source` field rather than a Slack name:

```python
class FileCleaned(BaseEvent):
    source: str            # "slack" | "gmail" | "linear"
    file: str
    rules_fired: list[str]
```

**Library first (NFR-7).** LlamaIndex ships an `instrumentation` module — `Dispatcher`,
`BaseEvent`, `BaseEventHandler`, `BaseSpan`, `@dispatcher.span` — available since
llama-index-core 0.10.20; we pin 0.14.24. We define our events and one handler; we do not
write a tracing framework, and we do not add a third-party dependency.

Our stages emit on the same dispatcher the library's own stages use, so one run produces one
trace covering our cleaning and parsing *and* the library's embedding and retrieval calls.

Ingestion only for now. Query-time tracing is designed when SLACK-12 exists and there is
something to trace.

### Acceptance Criteria

```gherkin
Scenario: a stage emits a structured event
  Given the cleaning stage processes one file
  When it finishes
  Then it emits a FileCleaned event carrying source, name, rules_fired and byte deltas

Scenario: a failure is an event, not a traceback on stderr
  Given a file that raises inside a stage
  Then a FileFailed event carries source, the file name and the exception type
  And the run continues to the next file

Scenario: the handler writes one JSON object per line
  Given a handler attached to the dispatcher
  Then each event becomes one line of JSON under data/<source>/logs/<run_id>.jsonl
  And the run summary at the end reports per-stage counts and elapsed time

Scenario: spans cover a stage, not a file
  Given a stage decorated with @dispatcher.span
  Then one span covers the whole stage and the per-file events sit inside it

Scenario: observability never changes the output
  Given the same corpus cleaned with the handler attached and detached
  Then every clean_sha256 is identical
```

The last scenario is the one that matters: instrumentation is allowed to observe the run and
never to alter it (NFR-1).

### Example with real data

```json
{"event":"FileCleaned","source":"slack","file":"dsid_0161f905...__1719998880-cred-cleanup....txt",
 "rules_fired":["unescape_newline","trailing_whitespace","final_newline"],
 "bytes_in":3294,"bytes_out":3268}
{"event":"StageDone","source":"slack","stage":"clean","files":285605,"failed":0,"seconds":412.8}
```

The same two lines, with `"source":"gmail"`, are what the Gmail branch will emit.

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** one event class per thing worth counting, named after the thing rather than
  the source or the stage that happens to emit it today. A fourth source adds a value to
  `source`, not a new module.
- **Observable:** the run summary is the artefact a future reader checks first; the manifest
  answers *what changed in this file*, the log answers *what happened during this run*.
- **Dependency discipline:** no new third-party dependency. `llama-index-core` is already
  pinned and carries the whole instrumentation module.

### Dependencies

APIs data contracts: none · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-4  `write_clean_corpus(archives_dir, clean_dir)` ⬜

**Status** To do
**As a** pipeline that has to prove which raw bytes produced which clean bytes
**I want to** every thread cleaned once into `data/slack/clean/`, with a manifest beside it
**So that** the cleaning step has the audit trail the Confluence one has

Mirrors PARSE-2. One row per file: name, `raw_sha256`, `clean_sha256`, and which rules fired.

**Library first (NFR-7):** the cleaning functions implement LlamaIndex's `Transformation`, so
they run inside an `IngestionPipeline` and get its `IngestionCache` — a re-run skips every
node+transformation pair it has already done, which is most of what a hand-written resume
would do. The manifest stays anyway: the docstore tracks document identity, not which raw
bytes produced which clean bytes.

### Acceptance Criteria

```gherkin
Scenario: the corpus is written once
  Given the 58 zip slices
  When I run write_clean_corpus
  Then data/slack/clean/ holds 285,605 files under their original names
  And data/slack/clean/_manifest.json holds one row per file

Scenario: the manifest records what happened
  Then each row carries raw_sha256, clean_sha256 and the rules that fired
  And the per-rule totals match the counts in SLACK-1 and SLACK-2

Scenario: re-running changes nothing
  When I run it a second time
  Then every clean_sha256 is unchanged
```

### Example with real data

```json
{ "name": "dsid_0161f905...__1719998880-cred-cleanup-rotation-playbook-checkin.txt",
  "raw_sha256": "sha256:...",
  "clean_sha256": "sha256:...",
  "rules": ["unescape_newline", "trailing_whitespace", "final_newline"] }
```

### Non-functional Requirements

Shared list, plus:

- **Observable:** this is the first stage that runs at corpus scale, so it is the first caller
  of the SLACK-3 dispatcher — one span for the stage, one event per file, one summary at the
  end. A failed file is an event and the run continues.
- **Restartable (NFR-3):** a second run skips work already done, via the `IngestionCache`, and
  ends with identical `clean_sha256` values.
- **Maintainable:** the only module in the cleaning stage allowed to touch disk. SLACK-1 and
  SLACK-2 stay pure, which is what makes them testable on strings.
- Plus a golden fingerprint over the manifest in the Confluence pattern, so a later refactor
  that changes one byte of one file fails a test.

### Dependencies

APIs data contracts: SLACK-1, SLACK-2, SLACK-3 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-5  `channel_of(text, filename) -> str` ⬜

**Status** To do
**As a** retrieval pipeline that ranks `postmortems` above `lunch-plans`
**I want to** the channel of every thread, including the 4.1% that do not state one on line 1
**So that** 3,037 documents keep their routing metadata instead of falling into `unknown`

### Acceptance Criteria

```gherkin
Scenario: line 1 is a channel name
  Given a thread whose first line is "customer-success"
  Then channel_of returns "customer-success"

Scenario: line 1 is an export path
  Given a thread whose first line is
        "sources/slack/eng-ml/3312349999-photon9b-int4-econ-flagging-guidance.json"
  Then channel_of returns "eng-ml"

Scenario: no channel anywhere
  Given a thread whose first line is "1719998880"
  Then channel_of returns "unknown"

Scenario: the corpus totals hold
  When I run channel_of over all 285,605 files
  Then 273,519 return one of the 36 known channels
  And 3,037 are recovered from an export path
  And 8,790 return "unknown"
```

### Example with real data

| file | line 1 | returns |
|---|---|---|
| `dsid_a4e702bd...__1793045678-novacare-vra-check.txt` | `customer-success` | `customer-success` |
| `dsid_d6bc004c...__3312349999-photon9b-int4-...txt` | `sources/slack/eng-ml/...json` | `eng-ml` |
| `dsid_0161f905...__1719998880-cred-cleanup-...txt` | `1719998880` | `unknown` |

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** the three steps are an ordered table of named strategies — `line1`,
  `export_path`, `unknown` — so a fourth recovery route is a row with its own corpus count.
- **Observable:** the strategy that won is recorded per file, so the 3,037 / 8,790 split is a
  number the run reports rather than a claim in a document.
- A channel name is lowercase letters, digits, `-`, `_` and spaces, at most 40 characters, and
  never starts with a digit — that last clause is what keeps a bare timestamp out.

### Dependencies

APIs data contracts: SLACK-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-6  `split_messages(text) -> list[str]` ⬜

**Status** To do
**As a** parser that must not cut a message in half
**I want to** the message boundaries of a thread, in both export layouts
**So that** every later story counts speakers and turns correctly

Runs on the clean corpus (SLACK-4), so escaping and stray indentation are already gone.

Two layouts exist. Most threads separate messages with a blank line; about 3% put one
message per line. A fenced code block may contain blank lines, so a blank line is not
always a boundary. The rule is the speaker line, not the blank line.

### Acceptance Criteria

```gherkin
Scenario: blank-line layout with a multi-line message
  Given a message whose text continues on the next line
  When I split the thread
  Then the continuation stays inside the same message

Scenario: one-message-per-line layout
  Given a thread whose first line is "1772201234-llm-cafe-antics.json"
  When I split the thread
  Then each line that opens with a speaker line is its own message

Scenario: a blank line inside a fenced code block
  Given a message containing a ``` fence with a blank line in it
  When I split the thread
  Then the fence stays inside one message
```

### Example with real data

Before, from `dsid_a4e702bd...__1793045678-novacare-vra-check.txt`:

```text
Aisha (CS): Hey team - NovaCare sent an updated vendor risk assessment and DPA follow-up.
Can someone pick this up? Link: https://files.redwoodinternal/vra/novacare_2026.pdf :eyes:

Priya (Onboarding): I can take lead on the questionnaire.
```

After: 2 messages, the first of them 2 lines long.

### Non-functional Requirements

Shared list. Byte-preserving: joining the returned messages back with their separators
reproduces the input exactly.

### Dependencies

APIs data contracts: SLACK-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-7  `parse_speaker(line) -> (name, role, is_bot)` ⬜

**Status** To do
**As a** design that treats a role taxonomy as signal real Slack does not have
**I want to** the speaker, their role and whether they are a bot, off the message's first line
**So that** a chunk can say who spoke and a bot's output can be told from a human's

### Acceptance Criteria

```gherkin
Scenario: name with a role
  Given the line "Aisha (CS): Hey team"
  Then parse_speaker returns ("Aisha", "CS", False)

Scenario: a bot
  Given the line "questionnaire-bot: Received nova-care_vra_2026.pdf"
  Then parse_speaker returns ("questionnaire-bot", None, True)

Scenario: naming styles that appear in the corpus
  Given the lines "jen_sales: ...", "alex-cust: ...", " tom_ae: ..."
  Then each returns its name with the leading space stripped and role None

Scenario: not a speaker line
  Given the line "Due: 2026-04-02"
  Then parse_speaker returns None
```

The last scenario is the sharp edge: a body line such as `Due: 2026-04-02` or
`status: pending` also contains a colon. A name is at most 40 characters, has no sentence
punctuation, and the colon must be followed by a space.

### Example with real data

| line | name | role | is_bot |
|---|---|---|---|
| `Aisha (CS): Hey team` | `Aisha` | `CS` | false |
| `build-bot: nightly-personas deployed` | `build-bot` | `None` | true |
| ` tom_ae: FYI customer claims ...` | `tom_ae` | `None` | false |
| `Due: 2026-04-02` | — | — | — |

### Non-functional Requirements

Shared list.

### Dependencies

APIs data contracts: SLACK-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-8  `parse_thread(path) -> Thread` + the truth set ⬜

**Status** To do
**As a** pipeline that will trust the parser 285,605 times
**I want to** one record per thread, and ~50 hand-checked threads that prove the parser right
**So that** a parsing regression fails a test instead of quietly poisoning the index

Follows PARSE-17's pattern: hand-decide the correct output on real files first, then assert
against it. Sample the 50 across both layouts, the `unknown` channel case, threads with
fenced code, and the bot-heavy ones.

### Acceptance Criteria

```gherkin
Scenario: one thread becomes one record
  When I parse dsid_a4e702bd...__1793045678-novacare-vra-check.txt
  Then the record has channel "customer-success", thread_ts 1793045678,
       slug "novacare-vra-check", 5 participants and 16 messages

Scenario: the truth set holds
  Given 50 hand-checked threads under tests/golden/slack_truth.json
  Then parse_thread reproduces every message boundary and speaker in them
```

### Example with real data

```json
{ "doc_id": "a4e702bd03254699b0e7bed0000972ab",
  "channel": "customer-success",
  "thread_ts": 1793045678,
  "slug": "novacare-vra-check",
  "participants": ["Aisha", "Ben", "Priya", "Tom", "questionnaire-bot"],
  "message_count": 16,
  "messages": [
    {"turn": 0, "speaker": "Aisha", "role": "CS", "is_bot": false,
     "text": "Hey team - NovaCare sent an updated vendor risk assessment..."},
    {"turn": 4, "speaker": "questionnaire-bot", "role": null, "is_bot": true,
     "text": "Received nova-care_vra_2026.pdf. Extracted fields: ..."}
  ] }
```

### Non-functional Requirements

Shared list.

### Dependencies

APIs data contracts: SLACK-5, SLACK-6, SLACK-7 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-9  `chunk_thread(thread) -> list[Chunk]` ⬜

**Status** To do
**As a** retrieval index whose unit is the conversation
**I want to** one chunk per thread, split only when a thread is over budget
**So that** 99% of threads reach the embedder whole

Measured: thread tokens are p50 821, p90 1,256, p99 1,725, max 3,101. At a 2,048-token ceiling
about 99% of threads never split. Unlike Confluence, where every page was split, splitting here
is the exception — `SentenceSplitter` runs on the tail only, never by default.

### Acceptance Criteria

```gherkin
Scenario: a normal thread is one chunk
  Given a thread of 821 tokens and a ceiling of 2,048
  Then chunk_thread returns one chunk holding the whole thread

Scenario: an over-budget thread splits on a message boundary
  Given a thread of 3,101 tokens and a ceiling of 2,048
  Then it splits into 2 chunks
  And no message is cut in half
  And every message lands in exactly one chunk

Scenario: ids are stable
  Then a chunk id is sha256(doc_id:first_turn:last_turn) and does not change between runs
```

### Example with real data

`dsid_a4e702bd...__1793045678-novacare-vra-check.txt`, 16 messages, about 780 tokens: one
chunk, first_turn 0, last_turn 15.

### Non-functional Requirements

Shared list.

### Dependencies

APIs data contracts: SLACK-8 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-10  `to_text_node(chunk) -> TextNode` ⬜

**Status** To do
**As a** vector that has to carry who spoke and where
**I want to** a chunk turned into a LlamaIndex `TextNode` with the right metadata and templates
**So that** channel and participants reach the embedder without us hand-building a header

**Checked against the library first (NFR-7).** A `TextNode` already renders
`text_template='{metadata_str}\n\n{content}'` with `metadata_template='{key}: {value}'`, and
`excluded_embed_metadata_keys` keeps a field on the node but out of the embedded text. So this
story sets fields and templates; it does not build a string.

The tension it has to manage: a header helps the vector carry channel and participants, but an
identical prefix on every chunk pushes 285,605 vectors toward each other. Keep the embedded
keys to the two that carry meaning, and exclude the bookkeeping ones.

### Acceptance Criteria

```gherkin
Scenario: identity fields ride on the node but not in the embedding
  Given a chunk of the NovaCare thread
  Then the node metadata holds channel, participants, doc_id, content_hash
  And doc_id and content_hash are in excluded_embed_metadata_keys
  And channel and participants are not

Scenario: an unknown channel contributes nothing to the text
  Given a thread whose channel is unknown
  Then "unknown" does not appear in the embedded text

Scenario: no invented date
  Then no timestamp appears in the node metadata or the embedded text

Scenario: the node id is stable
  Then node.id_ is the chunk id from SLACK-9 and survives a re-run
```

The third scenario is not a style rule. The corpus timestamps are placeholders — 73,578
distinct values over 285,605 files, years running 2001 to 2513 — so a date would be noise.

### Example with real data

`get_content(MetadataMode.EMBED)` for the NovaCare thread:

```text
channel: customer-success
participants: Aisha (CS), Priya (Onboarding), Ben (Security), Tom (Legal), questionnaire-bot

Aisha (CS): Hey team - NovaCare sent an updated vendor risk assessment and DPA follow-up...
Priya (Onboarding): I can take lead on the questionnaire...
```

`doc_id` and `content_hash` are on the node, and absent from the text above.

### Non-functional Requirements

Shared list, and NFR-7: the rendering is the library's, not ours.

### Dependencies

APIs data contracts: SLACK-9 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-11  Embed + BM25 hybrid index ⬜  *(module-level; split when we reach it)*

Nodes from SLACK-10 go through an `IngestionPipeline` into the vector store, with a docstore
keyed on the dsid so `refresh_ref_docs` handles re-runs, plus a `BM25Retriever` beside the
vectors and a `QueryFusionRetriever` over the two. All library code — see section 8 of the
design for the audit.

**BM25 is required, not optional.** 72.8% of threads carry an exact-match token — `r_9f8e7d6c`,
`OF-ACME-001`, `Photon9B-int4` — that dense retrieval alone loses. 56.2% carry a URL and 72.8%
a fenced code block, which push the same way.

Every node carries `channel`, `participants`, `doc_id`, `content_hash` and `embedding_model`.
It does **not** carry a date: see SLACK-9.

Channel is also an authority signal available for free: `postmortems` and `incidents` are
verified outcomes, `random` and `lunch-plans` are not.

---

## SLACK-12  recall@20 on the benchmark questions ⬜  *(module-level; split when we reach it)*

Mirrors PARSE-16. Needs `questions.jsonl` from the v1.0.0 release, filtered to the questions
whose gold documents are Slack.

| variant | decides |
|---|---|
| dense only | the floor |
| hybrid, dense + BM25 | whether BM25 earns its place |
| hybrid + channel authority | whether the free metadata signal helps |

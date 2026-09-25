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
  optional team or role in brackets or after ` - `, colon, space.
- **dsid**: the document id in the filename, `dsid_<32 hex>__<unix_ts>-<slug>.txt`. Unique
  across all 285,605 files, so it is the id. The timestamp beside it is **not** a date: only
  75,272 distinct values cover the corpus, 1,069 files share `1765432100`, the years run from
  2001 to 2513, and the values are keyboard walks (`1923456789`). Do not treat it as a time,
  and do not rank on recency. There are no per-message timestamps anywhere in the corpus.
- **Chunk**: what goes to the embedder. One thread, unless the thread is over the token
  ceiling, in which case it splits on a message boundary. About 99% of threads are one chunk.
- **TextNode**: LlamaIndex's unit. Our custom `NodeParser`s (SLACK-9, 10) make them inside
  LlamaIndex's `IngestionPipeline`; everything downstream of a node is library code — see
  section 8 of the design.

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
   `indented_speaker` on 1,489. If a refactor moves a count, a test fails and says by how
   much. A rule with no measured count is a rule nobody has justified.
4. **Dependency discipline.** A story that wants a third-party dependency has to say which
   LlamaIndex component it rejected and why (NFR-7). So far none has needed one.

| Story | Status |
|---|---|
| SLACK-0  Corpus profile | ✅ |
| SLACK-1  `unescape` | ✅ |
| SLACK-2  `normalize_whitespace` | ✅ |
| SLACK-3  events and a handler  *(shared by every source)* | ✅ |
| SLACK-4  `write_clean_corpus` + manifest | ✅ |
| SLACK-5  `channel_of` | ✅ |
| SLACK-6  `split_messages` | ✅ |
| SLACK-7  `parse_speaker` | ✅ |
| SLACK-8  `parse_thread` | ✅ |
| SLACK-8b  truth set | ✅ |
| SLACK-6b  label words from the truth set | ✅ |
| SLACK-9  `SlackThreadParser` (custom `NodeParser`) | ⬜ |
| SLACK-10  `SlackMessageChunker` | ⬜ |
| SLACK-11  Ingestion run: reader, pipeline, stores, hybrid retrieval | ⬜ |
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

## SLACK-2  `normalize_whitespace(text) -> WhitespaceResult` ✅

**Status** Done
**As a** speaker parser that anchors on the start of a line
**I want to** indented speaker lines straightened and the other whitespace defects repaired
**So that** ` tom_ae: FYI ...` parses as a message rather than as body text

`pipeline/slack/whitespace.py`, run on SLACK-1's output. Pure: text in,
`WhitespaceResult(text, rules_fired)` out. `RULES` is a table of (name, function) in the
order they run; each function does one thing and returns the new text and its change count.

**The trap, measured.** A speaker line is indented by exactly one space or one tab. The same
shape is also an HTTP header or YAML pasted outside a fence (` Host: api.redwood.example`,
` enabled: true`), and deeper indents (`  max_retries: 5`) are always YAML or code. So the
indent goes only when all of these hold:

1. the line is outside a code block. Any line with an odd number of ``` opens or closes one,
   wherever the fence sits: `kai: logs:```` opens a block. 39,786 threads open a fence mid-line.
2. it is indented by one space or one tab, then `name: ` or `name (role): `.
3. it starts a message (follows a blank line), or its name speaks at least twice in the thread.

That straightens 1,489 threads. Rule 3 leaves 59 more threads indented: mostly headers and
YAML, but also some real one-off speakers in threads without blank lines between messages
(`deploy-bot: Deploy started ...`). Better that than headers turned into fake messages;
SLACK-7 can still read an indented speaker.

**The design doc's numbers do not reproduce.** It quotes 27,225 threads with an indented
speaker line; no reading of "indented speaker" gets near that (any one-space or one-tab
`name:` line outside code: 1,548). Its "3+ consecutive blank lines: 448" matches runs of two
or more blank lines (476 after SLACK-1), which is what this collapses: messages are separated
by exactly one blank line. The story's sales example quoted the thread without its blank
lines; the real thread has one between every message.

### Acceptance Criteria

```gherkin
Scenario: an indented speaker line is straightened
  Given "\n\n tom_ae: FYI customer claims integrations built during POC..."
  Then it becomes "tom_ae: FYI customer claims integrations built during POC..."

Scenario: YAML, headers and list items keep their indent
  Given " enabled: true" or " Host: api.redwood.example" inside a message, or "  - Verify SOC2"
  Then it is unchanged

Scenario: indentation inside a code block is left alone
  Given an indented line after "kai: logs:```" and before the closing ```
  Then it is unchanged, whatever it looks like

Scenario: the remaining whitespace rules
  Given a CR, a non-breaking space, trailing spaces, or 2+ blank lines in a row
  Then CR becomes LF, nbsp becomes a space, trailing whitespace goes, blank runs collapse to one
  And the file ends with exactly one newline; an empty thread stays empty
```

### Example with real data

Before, the `sales` thread `jen_sales: Quick sync - ACME PoC is greenlighted...`:

```text
jen_sales: Quick sync — ACME PoC is greenlighted but procurement raised 3 blocking items...

 tom_ae: FYI customer claims integrations built during POC must remain theirs.

 sana_se: I reviewed the deliverables — POC outputs are config + prompt recipes...
```

After: the same three messages, none of them indented.

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** one `RULES` table, applied in the stated order: carriage_return,
  non_breaking_space, indented_speaker, trailing_whitespace, blank_line_run, final_newline.
  CR goes first so every later rule sees plain lines.
- **Pure:** no disk, no dispatcher call. Returns text plus the rules that fired.
- **Corpus counts as tests** (`test_files_each_rule_fires_on_after_unescape`, on SLACK-1's
  output): final_newline 236,927, trailing_whitespace 66,893, indented_speaker 1,489,
  blank_line_run 476, carriage_return 269, non_breaking_space 55.

### Dependencies

APIs data contracts: SLACK-1 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-3  `pipeline/observability.py`: events and a handler ✅  *(shared by every source)*

**Status** Done
**As a** person about to run a pipeline over 285,605 files on a laptop
**I want to** every stage to say what it did, through LlamaIndex's own instrumentation
**So that** a run that stalls, skips or errors can be diagnosed without rerunning it under a debugger

**This story is not Slack-specific.** Gmail and Linear have the same need, so the module sits
at `pipeline/observability.py`, outside `pipeline/slack/`, and imports nothing from any source.
It landed stacked after SLACK-1 and SLACK-2 (their story-index rows sit next to its row, so
separate branches off master would conflict); the other source branches take it from master
once it merges. The events carry a `source` field rather than a Slack name:

```python
class FileCleaned(PipelineEvent):   # PipelineEvent = BaseEvent with a UTC timestamp
    source: str                      # "slack" | "gmail" | "linear"
    file: str
    rules_fired: dict[str, int]      # rule -> changes, as SLACK-1 and SLACK-2 return them
    bytes_in: int
    bytes_out: int
```

What was built: `FileCleaned`, `FileFailed`, `StageDone`, a `JsonLinesEventHandler`, and
`events_logged_to(log_path)`, which attaches the handler to LlamaIndex's **root** dispatcher
for the length of a `with` block. Root, because LlamaIndex's own events only travel upward:
a handler on our `pipeline` dispatcher would never see an embedding event. Reviewed by a
code-review agent; its fixes (root dispatcher, UTC ISO timestamps, no silent `default=str`,
detach by identity so a crash inside the block is not masked) are in, each with a test.

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
{"event": "FileCleaned", "timestamp": "2026-09-24T02:29:00.898578Z", "span_id": "write_clean_corpus-dfd9fade-...",
 "tags": {}, "source": "slack", "file": "dsid_919525fd...__1814012345-morning-riddle-and-wfh-poll.txt",
 "rules_fired": {"unescape_newline": 17, "unescape_quote": 8, "final_newline": 1},
 "bytes_in": 1324, "bytes_out": 1300}
{"event": "StageDone", "timestamp": "2026-09-24T02:29:43.109153Z", "span_id": "write_clean_corpus-dfd9fade-...",
 "tags": {}, "source": "slack", "stage": "clean", "files": 285605, "failed": 0, "seconds": 44.4}
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

## SLACK-4  `write_clean_corpus(archives_dir, clean_dir)` ✅

**Status** Done
**As a** pipeline that has to prove which raw bytes produced which clean bytes
**I want to** every thread cleaned once into `data/slack/clean/`, with a manifest beside it
**So that** the cleaning step has the audit trail the Confluence one has

`pipeline/slack/corpus.py`, run with `uv run python -m pipeline.slack.corpus`. It reads the
58 zips directly, runs SLACK-1 then SLACK-2 on each thread, writes it under its own name, and
writes `_manifest.json`: one row per file with name, `raw_sha256`, `clean_sha256` and the
rules that fired. SLACK-1's rules get an `unescape_` prefix, because both stages have a
`carriage_return` rule and they mean different things. It is the only module of the stage
that touches disk. It imports no Confluence code: `pipeline/corpus.py` reads a folder, not
zips, and writes Confluence manifest rows.

**The full run, measured:** 285,605 threads, 0 failed, 1.4 GB; 44 s into an empty folder, 67 s
when it also replaces a previous run's folder. The manifest's per-rule
totals equal the SLACK-1 and SLACK-2 corpus pins exactly: unescape_newline 8,334,
unescape_quote 4,083, unescape_backslash 787, unescape_unicode 147, unescape_tab 36,
unescape_carriage_return 19, unescape_slash 14, final_newline 236,927, trailing_whitespace
66,893, indented_speaker 1,489, blank_line_run 476, carriage_return 269,
non_breaking_space 55.

**Library first, and why not `IngestionPipeline` here (NFR-7).** The story planned to run the
cleaners as LlamaIndex `Transformation`s inside an `IngestionPipeline` with an
`IngestionCache`. We did not: this stage's output is files and a manifest, not nodes;
`IngestionCache` would hold all 285,605 threads in memory to save a rerun of about a minute;
and the manifest already proves which raw bytes made which clean bytes. The pipeline belongs
where nodes first exist (SLACK-9 to 11). Observability does use the library: one
`@dispatcher.span` over the stage and SLACK-3's events on it.

### Acceptance Criteria

```gherkin
Scenario: the corpus is written once
  Given the 58 zip slices
  When I run write_clean_corpus
  Then data/slack/clean/ holds 285,605 files under their original names
  And data/slack/clean/_manifest.json holds one row per file, in name order

Scenario: the manifest records what happened
  Then each row carries raw_sha256, clean_sha256 and the rules that fired
  And the per-rule totals match the counts in SLACK-1 and SLACK-2

Scenario: a file that fails is an event, and the run goes on
  Given a thread that is not valid UTF-8
  Then a FileFailed event names it, it gets no clean file and no manifest row
  And StageDone reports files and failed

Scenario: re-running changes nothing, and neither does logging
  When I run it a second time, with or without a log attached
  Then every row is unchanged
```

### Example with real data

```json
{"name": "dsid_919525fd7c2944db922e298431b6e366__1814012345-morning-riddle-and-wfh-poll.txt",
 "raw_sha256": "...", "clean_sha256": "...",
 "rules": {"unescape_newline": 17, "unescape_quote": 8, "final_newline": 1}}
```

and its event in `data/slack/logs/clean-<time>-<id>.jsonl`: `bytes_in` 1,324, `bytes_out` 1,300.

**Reviewed** by a code-review agent. It confirmed that the real run was correct: 285,605 unique names, and
manifest rows, files on disk and `clean_sha256` values all agree. It found four bugs that the
corpus does not trigger today, now fixed with a test each:
- a repeated name overwrote the first file; it is now a `DuplicateName` failure
- files from an earlier run survived; the staging folder swap fixes this
- a corrupt zip member or zip stopped the whole run; it is now a `BadZipFile` failure for that entry
- a half-written file could stay on disk; it is now deleted
A bug in the cleaners still stops the run on purpose: across 285k files, a broad `except`
would hide it.

### Non-functional Requirements

Shared list, plus:

- **Observable:** one span for the stage, one event per file, one StageDone at the end. The
  entry point writes the log to `data/slack/logs/`.
- **Restartable (NFR-3):** a rerun rewrites every file with identical bytes. It writes into
  `clean.staging/` and swaps it in at the end, so `clean/` never mixes two runs and always holds
  exactly the files its manifest lists; a crash mid-run leaves the previous `clean/` intact.
- **Maintainable:** the only disk-touching module of the stage; SLACK-1 and SLACK-2 stay pure.
- **Golden fingerprint:** `test_slice_0003_fingerprint` hashes the manifest rows of one real
  slice (5,000 threads), so a later change to one byte of one file fails a test.

### Dependencies

APIs data contracts: SLACK-1, SLACK-2, SLACK-3 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-5  `channel_of(text) -> Channel` ✅

**Status** Done
**As a** retrieval pipeline that ranks `postmortems` above `lunch-plans`
**I want to** the channel of every thread, including those that do not state one on line 1
**So that** 3,036 more documents keep their routing metadata instead of falling into `unknown`

`pipeline/slack/channel.py`. Pure: the text of one clean thread (SLACK-4's output) in,
`Channel(name, route)` out. `ROUTES` is an ordered table; the first route that names a known
channel wins.

| route | line 1 looks like | threads |
|---|---|---|
| `line1` | `customer-success` | 273,516 |
| `export_path` | `sources/slack/eng-ml/3312349999-photon9b-int4-econ-flagging-guidance.json` (943) or `slack/product/1842501234-keys-create-emptystate-presets-accessibility.json` (2,093) | 3,036 |
| `unknown` | `1719998880`, `2112345678-burst-header-backcompat-checkin.json`, `Elena: Quick sync ...` | 9,053 |

**Known channels are a table, not a pattern.** SLACK-0 found 130 channel-shaped words on line
1. `KNOWN_CHANNELS` holds the 35 that head 3 or more threads on different subjects. The other
94 each head one thread: topic slugs (`kv-residency-sim-harness-sync`) or stray words
(`incident-3781`, `degraded`). `sales-poc-benchmark` heads 3 threads, but they are near-copies
of one NovaRetail scenario (same AE, same numbers), so it is a topic too, unlike
`watercooler`, whose 3 threads are about three different things. Every export-path channel
but one (`temp-alerts`, 1 thread) is among the 35.

**Only line 1 is read.** A path or `#channel` further down is a mention of another channel,
not where the thread lives. The story's `filename` argument was dropped: no route uses it.

**The design doc's export-path count holds; its unknown count is 263 off.** A path with or
without the `sources/` prefix: 943 + 2,093 + 1 (`temp-alerts`) = 3,037, the doc's number, of
which 3,036 name a known channel. (The first version of this story matched only `sources/`
and found 943; the review caught it.) Unknown is 9,053 (3.2%), not 8,790. By line 1:
bare `<ts>-<slug>.json` with no channel 2,343, epoch number 4,213, prose summary 1,329, speaker
line 1,014, stray slug 135, blank 15, the 3 `sales-poc-benchmark` threads and the 1 `temp-alerts`
path.

### Acceptance Criteria

```gherkin
Scenario: line 1 is a channel name
  Given a thread whose first line is "customer-success"
  Then channel_of returns Channel("customer-success", "line1")

Scenario: line 1 is an export path, with or without "sources/"
  Given a thread whose first line is
        "sources/slack/eng-ml/3312349999-photon9b-int4-econ-flagging-guidance.json"
        or "slack/product/1842501234-keys-create-emptystate-presets-accessibility.json"
  Then channel_of returns Channel("eng-ml", "export_path") or Channel("product", "export_path")

Scenario: no channel on line 1
  Given a first line "1719998880", a bare "<ts>-<slug>.json", a message, a topic slug or nothing
  Then channel_of returns Channel("unknown", "unknown")

Scenario: the corpus totals hold
  When I run channel_of over all 285,605 clean files
  Then 273,516 come from line 1, 3,036 from an export path and 9,053 are unknown
```

### Example with real data

| file | line 1 | returns |
|---|---|---|
| `dsid_a4e702bd...__1793045678-novacare-vra-check.txt` | `customer-success` | `Channel("customer-success", "line1")` |
| `dsid_d6bc004c...__3312349999-photon9b-int4-...txt` | `sources/slack/eng-ml/...json` | `Channel("eng-ml", "export_path")` |
| `dsid_0161f905...__1719998880-cred-cleanup-...txt` | `1719998880` | `Channel("unknown", "unknown")` |

### Non-functional Requirements

Shared list, plus:

- **Maintainable:** `ROUTES` is an ordered table of named finders; a new recovery route is a
  row with its own corpus count. `KNOWN_CHANNELS` is the other table.
- **Observable:** the winning route is returned with the channel, so SLACK-8 can record it
  per thread and the run can report the split.
- **Corpus counts as tests** (`test_routes_and_channels_over_the_clean_corpus`): line1
  273,516, export_path 3,036, unknown 9,053, and the thread count of every one of the 35
  channels.

**Reviewed** by a code-review agent. Its catch is the `slack/` path without `sources/` (2,093
threads recovered). Also from the review: `sales-poc-benchmark` dropped, every channel count
pinned, and edge cases pinned as deliberate (CRLF works; `Incidents`, `#incidents` and a
BOM are unknown, and none occurs in the corpus).

### Dependencies

APIs data contracts: SLACK-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-6  `split_messages(text) -> Split` ✅

**Status** Done
**As a** parser that must not cut a message in half
**I want to** the message boundaries of a thread, in both export layouts
**So that** every later story counts speakers and turns correctly

`pipeline/slack/messages.py`. Pure: the text of one clean thread (SLACK-4) in,
`Split(header, messages)` out, and `header + "".join(messages) == text` byte for byte on all
285,605 threads. The header is what comes before the first message (channel line, export
path, summary); each message keeps its own trailing line breaks.

**The rule is the speaker line, not the blank line.** A message opens at a line, outside a
code block, that starts with a speaker. That covers both layouts, which are far closer in
size than the story assumed ("about 3% one per line"):

| layout | threads |
|---|---|
| blank line between messages | 149,429 |
| one message per line | 108,460 |
| mixed | 24,281 |
| no speaker line at all | 3,435 |

12,569 threads have a blank line inside a code block, which is why a blank line cannot be the
boundary.

**Speaker shapes, all measured:** `tom_ae:`, `Aisha (CS):`, full names `Maya Chen:` and
`Priya S.:` (40,141 threads), `Maya - People Ops:` (16,754 lines), lowercase full names
`maria gonzalez:`, and bots `Incident Bot:`. A lowercase full name counts only if it opens two
or more lines in the thread, because the same shape is also a one-off label (`browser
console:`, `Edge log example:`).

**Labels are not speakers.** `NOT_SPEAKERS` holds the first words of labels measured opening a
line inside a message: `Due: 2026-04-02`, `Note:`, `Response:`, `Content-Type:`, `Plan B:`: 112
words in all. A name ending in `Bot` is always a speaker (`Status Bot:`). Team handles
(`ops:`, `legal:`, `support:`, `Customer Success:`) do speak, so they are not in the table.

**Reuse.** Code-block detection is SLACK-2's `code_fence_flags`. A fence left open at the end
of a thread (`sre-oncall: executing step A now.```, 1,434 threads) is treated as a typo so it
cannot swallow the messages after it. Checked and rejected: LlamaIndex's `SentenceSplitter`
and `TokenTextSplitter` cut by size, `MarkdownNodeParser`, `JSONNodeParser` and
`HTMLNodeParser` by markup, `SemanticSplitterNodeParser` by embedding distance, and
`SlackReader` reads the live API. None splits chat by speaker. `SentenceSplitter` returns in
SLACK-10, only for a single message longer than the ceiling.

**Result:** 5,741,020 messages; 62 threads have none (a bare list of handles, a key-value
dump, a lone dsid).

**Reviewed** by a code-review agent that sampled real threads, since there is no truth set
yet (SLACK-8b builds one). Precision of message starts was 298 of 300. It found about 54,000
missed speaker lines (lowercase full names, `Name - Team`, unclosed fences, 33 label words);
all are fixed, each with a test.

### Acceptance Criteria

```gherkin
Scenario: blank-line layout with a multi-line message
  Given a message whose text continues on the next line
  Then the continuation stays inside the same message

Scenario: one-message-per-line layout
  Given a thread whose first line is "1772201234-llm-cafe-antics.json"
  Then each line that opens with a speaker is its own message

Scenario: a blank line or a speaker shape inside a code block
  Given a message containing a ``` fence with a blank line and "raj: ..." in it
  Then the fence stays inside one message

Scenario: labels are not speakers
  Given "Due: 2026-04-02" or "Note: ..." at the start of a line
  Then it continues the message above it

Scenario: nothing is lost
  Then header + all messages joined equals the input, for every thread in the corpus
```

### Example with real data

`dsid_a4e702bd...__1793045678-novacare-vra-check.txt`: header `customer-success\n\n`, then 16
messages. Message 9 is Priya's task list, 5 lines, `Due: 2026-04-02` included:

```text
Priya (Onboarding): Added tasks:
- Verify SOC2 Type II (owner: Ben)
- Confirm DPA countersign (owner: Tom)
- Update onboarding tracker + risk flag (owner: Priya)
Due: 2026-04-02
```

### Non-functional Requirements

Shared list, plus:

- **Byte-preserving:** tested on every thread of the corpus.
- **Maintainable:** `NOT_SPEAKERS` is the label table; a new label is a word in it.
- **Corpus counts as tests:** 5,741,020 messages, 62 threads without one, NovaCare 16.
  *After SLACK-6b's 38 label words: 5,739,653 messages, 64 threads without one, NovaCare 16.*

### Dependencies

APIs data contracts: SLACK-4, SLACK-2 (`code_fence_flags`) · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-7  `parse_speaker(line) -> Speaker(name, team_or_role, is_bot)` ✅

**Status** Done
**As a** design that treats a role taxonomy as signal real Slack does not have
**I want to** the speaker, their team or role and whether they are a bot, off the message's first line
**So that** a chunk can say who spoke and a bot's output can be told from a human's

**Input.** The first line of one message from `split_messages` (SLACK-6). SLACK-6 has already
decided the line opens a message, so `parse_speaker` never sees a body line: whether
`Due: 2026-04-02` is a speaker or a label is SLACK-6's call (its `NOT_SPEAKERS` table), and
SLACK-2 has already straightened an indented speaker line such as ` tom_ae:`. This story only
reads the parts out of a line that is known to be a speaker line.

**The three shapes SLACK-6 accepts**, so the three this story must read:

| shape | real line | name | team_or_role |
|---|---|---|---|
| `Name: ` | `tom_ae: FYI customer claims ...` | `tom_ae` | `None` |
| `Name (Role): ` | `Aisha (CS): Hey team` | `Aisha` | `CS` |
| `Name - Team: ` | `Noah - AE: Verdigris wants a 10-day POC ...` | `Noah` | `AE` |

`pipeline/slack/speaker.py`. Pure: one message (or its first line) in, `Speaker(name,
team_or_role, is_bot)` out. It reuses SLACK-6's `SPEAKER_AT_LINE_START`, now with named groups
`name`/`after_dash`/`in_brackets`, so the two stories cannot disagree on the shapes. Every one of the
5,741,020 messages parses.

**Shapes, measured (messages):** name only 4,978,937 · in brackets 744,702 · after a dash
17,247 · both 134. 762,083 messages carry a `team_or_role`. *After SLACK-6b: 4,977,665 ·
744,607 · 17,247 · 134, and 761,988 with a `team_or_role`; the bot counts do not move.*

**Decisions:**
- **`team_or_role`, not `role`.** What sits beside the name is kept as written and not
  classified. It mixes teams (`CS` 21,799 messages, `People Ops` 21,193), job roles (`PM`
  23,533, `AE` 15,723), duties (`oncall` 48,853) and employers (`Customer - Acme Corp:` gives
  `Acme Corp`) across 7,334 distinct values; `SRE` and `Eng` could be either. Sorting them would be its own story, worth
  it only if SLACK-12 shows filtering by team helps.
- Both brackets and a dash (`Dan - HelixEdge (SI):`, 134): the brackets win. `HelixEdge` is
  not lost, since the speaker line stays in the message text.
- Team first (`Legal - Priya:`, roughly 800 by a first-name check, not pinned): read as
  written, name `Legal`. Nothing in the line says which part is the person. SLACK-8b's truth
  set can measure whether it matters.
- A line that is not a speaker line raises `ValueError`: it would mean a caller bug, since
  SLACK-6 only hands over speaker lines.
- Bots, `BOT_RULES`, first rule that fires, 573,797 messages in all: `name_ends_in_bot`
  (`deploy-bot`, `Incident Bot`, `DeployBot`) 573,157 · `name_starts_with_bot` (`bot-ci`) 444
  · `team_or_role_is_bot` (`evi (bot):`) 196. No person named like a bot was found; about 114 bot
  messages are missed (`BotCI:`, `bench-bot-2:`, `X - metrics-bot:`), 0.02%.

**Reuse.** No LlamaIndex component reads a chat speaker line; `SlackReader` gets the user from
the live API. The regex is SLACK-6's.

**Reviewed** by a code-review agent that checked the corpus: no correctness bugs. It corrected
two docstring claims (the team-first count, a false `talbot` false positive) and asked for
tests of the team-first decision, `bot_` and `(Bot)`; all done.

### Acceptance Criteria

```gherkin
Scenario: name with a team or role in brackets
  Given the line "Aisha (CS): Hey team"
  Then parse_speaker returns ("Aisha", "CS", False)

Scenario: name with a team after a dash
  Given the line "Ruth - Customer Success: Quick sync from today's all-hands Q&A"
  Then parse_speaker returns ("Ruth", "Customer Success", False)

Scenario: a bot
  Given the line "questionnaire-bot: Received nova-care_vra_2026.pdf"
  Then parse_speaker returns ("questionnaire-bot", None, True)

Scenario: naming styles that appear in the corpus
  Given the lines "jen_sales: ...", "alex-cust: ...", "tom_ae: ..."
  Then each returns its name as written and team_or_role None
```

A line SLACK-6 would not have cut on is outside this contract. The check that SLACK-6 cut in
the right places (labels such as `Due:` left inside a message) belongs to SLACK-8b.

### Example with real data

| line | name | team_or_role | is_bot |
|---|---|---|---|
| `Aisha (CS): Hey team` | `Aisha` | `CS` | false |
| `Priya - Design: Notes on the mock ...` | `Priya` | `Design` | false |
| `build-bot: canary run completed ...` | `build-bot` | `None` | true |
| `tom_ae: FYI customer claims ...` | `tom_ae` | `None` | false |

### Non-functional Requirements

Shared list.

### Dependencies

APIs data contracts: SLACK-6 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-8  `parse_thread(file_name, text) -> Thread` ✅

**Status** Done
**As a** pipeline that chunks and indexes threads
**I want to** one record per thread: its id, slug, channel, header and messages with speakers
**So that** later stories read fields instead of re-parsing text

`pipeline/slack/thread.py`. Pure, like SLACK-5, 6 and 7: the clean file's name and text in,
`Thread` out; the caller reads the file (SLACK-4 is the only story that touches disk). It
glues `channel_of` (SLACK-5), `split_messages` (SLACK-6) and `parse_speaker` (SLACK-7).

| field | from | notes |
|---|---|---|
| `doc_id` | file name, `dsid_<32 hex>__` | unique across 285,605 files; the id everywhere downstream |
| `slug` | file name, after the timestamp and `-` | `None` for the 6,199 files that have none (`dsid_…__2987654321.txt`, 26 of them ending `_1`); one name lacks the dash (`__1931234000Region-…` gives `Region-…`) |
| `channel` | `channel_of` | `Channel(name, route)`, `unknown` included |
| `header` | `split_messages` | text before the first message |
| `messages` | `split_messages` + `parse_speaker` | `Message(turn, speaker, text)`; `text` is the whole message, speaker line included |
| `participants` | the speakers | distinct names in the order they first speak |

**Not kept: the timestamp in the file name.** It is not a time (design section 5: keyboard
walks, years 2001 to 2513), so it is not a field anyone could misuse as one.

**The text survives whole:** `header + "".join(m.text for m in messages)` is the file text,
byte for byte.

**Result, all 285,605 files:** every name parses, 285,605 distinct `doc_id`s, 5,741,020
messages, 6,199 without a slug; every thread round-trips. Pinned in a real-data test. *After SLACK-6b: 5,739,653 messages.*

**Decisions:** the story was split; the truth set is SLACK-8b, so this PR stays one function.
The signature takes the name and text instead of a path, to stay pure. `messages` and
`participants` are lists, like SLACK-6's `Split`; a `Thread` is not hashable, which nothing
needs yet.

**Reviewed** by a code-review agent that ran the name pattern over every file: no
correctness bugs; it asked for the exact em dash in the example, the odd slug shapes in the
field table, and a stronger no-timestamp test; all done.

### Acceptance Criteria

```gherkin
Scenario: one thread becomes one record
  When I parse dsid_a4e702bd...__1793045678-novacare-vra-check.txt
  Then the record has doc_id "a4e702bd03254699b0e7bed0000972ab", slug "novacare-vra-check",
       channel "customer-success", 16 messages and participants
       Aisha, Priya, Ben, Tom, questionnaire-bot

Scenario: a file name without a slug
  When I parse dsid_5badc87efd7a49128d67b0234f809fa1__2987654321.txt
  Then slug is None

Scenario: a thread with no speaker line
  Then messages and participants are empty and the header is the whole text
```

### Example with real data

```json
{ "doc_id": "a4e702bd03254699b0e7bed0000972ab",
  "slug": "novacare-vra-check",
  "channel": {"name": "customer-success", "route": "line1"},
  "header": "customer-success\n\n",
  "participants": ["Aisha", "Priya", "Ben", "Tom", "questionnaire-bot"],
  "messages": [
    {"turn": 0, "speaker": {"name": "Aisha", "team_or_role": "CS", "is_bot": false},
     "text": "Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment..."},
    {"turn": 4, "speaker": {"name": "questionnaire-bot", "team_or_role": null, "is_bot": true},
     "text": "questionnaire-bot: Received nova-care_vra_2026.pdf. Extracted fields: ..."}
  ] }
```

### Non-functional Requirements

Shared list. Pure; the SLACK-5/6/7 corpus pins must not move.

### Dependencies

APIs data contracts: SLACK-5, SLACK-6, SLACK-7 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-8b  The truth set ✅

**Status** Done
**As a** pipeline that will trust the parser 285,605 times
**I want to** 50 hand-checked threads that prove `parse_thread` right
**So that** a parsing regression fails a test instead of quietly poisoning the index

Split out of SLACK-8 so each PR stays one function. Follows PARSE-17's pattern: decide the
correct output on real files first, then assert against it.

**The set.** `tests/fixtures/slack_truth/`: 50 real threads copied from `data/slack/clean/`
(so the test runs without the corpus) and `expected.json`, one entry per thread with `why`
(the reason it was sampled), `starts` ({line: [name, team_or_role, is_bot]} for every
message start) and `known_gaps` ({line: {reason, parser_says}}). The sample is seeded and
stratified: both layouts and mixed, `unknown` channel, export path, code blocks with blank
lines inside, bot-heavy threads, team-first lines, one-off capitalised speakers, a thread with
no speaker and a one-message thread. 862 message starts in all.

**How the truth was decided.** Five annotators labelled the threads blind: they read every
line and never saw the parser, its code or its output. Every disagreement with the parser
was then read in context by hand; in all 25 the annotator was right. A review agent then
re-read 23 threads (373 starts) line by line and found no wrong or missing start.

**Result:**

| | |
|---|---|
| message starts found by the parser | 871 (862 after SLACK-6b) |
| true message starts | 862 |
| parser starts that are true (precision) | 862 = 98.97% (100% after SLACK-6b) |
| true starts the parser found (recall) | 862 = 100% |
| speaker fields right on a true start | 846 of 862 |

The 25 known gaps:

| gap | lines | decision |
|---|---|---|
| a label word opens a false message: `Details:`, `Commands:`, `Files:`, `Expect:` | 4 | closed by SLACK-6b |
| a lowercase key inside a bot notice: `started_by: kyle`, `apply_log:`, `rollback_plan:` | 5 | closed by SLACK-6b |
| team written first: `IT - Priya:`, `CSM - Lena:`, `Facilities - Marco:` (3 threads) | 13 | accepted: about 800 of 5.74M lines (0.014%) across the corpus, so a swap rule is not worth its risk |
| a bot named in brackets: `Sam (ops-bot):` | 2 | accepted for now: 1,782 messages have a `(x-bot)` role on a non-bot name, and whether `ana (ops-bot)` is a person or the bot is unclear |
| `later - carla (eng-runtime):`, a time word read as the name | 1 | accepted: one line |

**Blind spot.** The truth is per line, so a message that starts mid-line cannot be marked:
one squashed thread joins about 15 messages on two lines (`...; chloe_sdk: ...`), and the
parser misses them too. The team-first rate on this set (13 lines) is inflated on purpose: 3
threads were sampled for it.

**Carried over from SLACK-6, now measured.** Across the corpus, 2,994 capitalised
single-word names (6,739 messages) never speak twice in any thread; the most frequent are
labels, not people: `Fallback` 71 threads, `Retry-After` 70, `Expect` 60, `Behavior` 59,
`Outputs` 49, `Rationale` 32, `User-Agent` 30. They are the input for SLACK-6b. A real
one-off speaker also lands in that list, so it is a list to read, not a rule.

### Acceptance Criteria

```gherkin
Scenario: the truth set holds
  Given 50 hand-checked threads under tests/fixtures/slack_truth/expected.json
  Then parse_thread reproduces every message start and speaker in them
  Except the known gaps, where it says exactly what the gap records
```

### Non-functional Requirements

Shared list. The fixtures are real data committed to the repo: 50 files, about 140 KB.

### Dependencies

APIs data contracts: SLACK-8 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-6b  Label words measured by the truth set ✅

**Status** Done
**As a** splitter that should not open a message on a label
**I want to** the label words SLACK-8b measured added to `NOT_SPEAKERS`
**So that** the known gaps close and the corpus pins move by a counted amount

`pipeline/slack/messages.py` gets a second table, `LABEL_NAMES`: 38 words that block a speaker
line only when the label is the **whole name**. `NOT_SPEAKERS` (112 words) still matches the
first word.

**How a word got in.** The candidates were the 9 SLACK-8b caught (`Expect`, `Details`,
`Commands`, `Files`, and the bot-notice keys `changes`, `started_by`, `apply_log`,
`rollback_plan`, `post-check`) and the most frequent capitalised names that never open two
lines in any thread. Each was read in 3 random real contexts; a word went in only if it was
a label in all of them:

| added | example |
|---|---|
| HTTP headers: `Retry-After`, `User-Agent`, `Request-ID`, `Transfer-Encoding` | `Retry-After: 30` after `HTTP/1.1 429` |
| findings after a code block: `Behavior`, `Outputs`, `Pattern`, `Notable`, `Interpretation`, `Conclusion`, `Responses` | `Pattern: intermittent 1–4s gaps in clusters.` |
| plan and review words: `Fallback`, `Canary`, `Start`, `Window`, `Rationale`, `Recommendation`, `Problem`, `Baseline`, `Dashboard`, `Bank`, `SDK`, `Python`, `FP16` | `Fallback: route -> eu-west4 on gate fail.` |
| option and hypothesis markers: `B`, `C`, `H1`, `H2`, `H3` | `H2: Redis cluster experienced a GC/backpressure...` |

**Not added:** `CI` (`CI (docs-bot): PR #5240 opened...` is a bot speaking) and `Everyone`
(`Everyone: ack?` addresses people; not a label in every context read).

**Why whole name, not first word.** A first-word match (the first version of this PR) also
silenced real speakers that start with one of these words and speak again in their thread:
`SDK Team:`, `SDK Lead:`, `SDK CI:`, and names typed with a stray space, `b en:`, `c raig:`.
Matching the whole name keeps them, at the cost of a few multi-word labels (`Start Date:`,
`Bank Note:`) still opening a message: 36 messages between the two versions.

**Result, all 285,605 threads:**

| | before | after |
|---|---|---|
| messages | 5,741,020 | 5,739,653 (1,367 false starts gone) |
| threads with no message | 62 | 64 |
| messages with a `team_or_role` | 762,083 | 761,988 |
| messages from bots | 573,797 | 573,797 |
| SLACK-8b parser starts / precision | 871 / 98.97% | 862 / 100% |
| SLACK-8b known gaps | 25 | 16 (the team-first, bracket-bot and `later` ones) |

The two new threads with no message were read by hand: neither has a speaker, and their only
"speaker" line was a label (`SDK: go-sdk v0.9.8`), so the old count held a fake message each.
NovaCare still has 16 messages.

### Acceptance Criteria

```gherkin
Scenario: a measured label no longer opens a message
  Given "ana: design uploaded\nFiles: a.svg\nExpect: 0 errors\nH1: ...\nRetry-After: 30\n"
  Then split_messages returns one message

Scenario: a new label word blocks only the whole name
  Given "kai: hi\nSDK: node-sdk 1.3.9\nSDK Team: PR #482 is ready\n"
  Then "SDK:" stays inside kai's message and "SDK Team" opens its own

Scenario: a bot named like a label still speaks
  Given "kai: hi\nCanary Bot: Canary deploy scheduled for rerank/v2 to 1% traffic.\n"
  Then split_messages returns two messages
```

### Dependencies

APIs data contracts: SLACK-6, SLACK-8b · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-9  `SlackThreadParser`: a custom LlamaIndex `NodeParser` ⬜

**Status** To do
**As a** pipeline that runs inside LlamaIndex's `IngestionPipeline`
**I want to** a `NodeParser` that turns one clean-thread `Document` into one `TextNode`
**So that** our parsing rules run as a library `Transformation`, and everything after the node is library code

`pipeline/slack/nodes.py`. A subclass of LlamaIndex's `NodeParser`, so it slots into
`IngestionPipeline(transformations=[...])` like `SentenceSplitter` does. Its one method,
`_parse_nodes`, is a thin wrapper: it calls `parse_thread` (SLACK-8) on the Document's text
and file name, and builds the node. The rules stay in SLACK-5 to 8; this story adds none.

**Checked against the library first (NFR-7).** No LlamaIndex parser splits chat by speaker
(`SentenceSplitter`, `TokenTextSplitter`, `SemanticSplitter` cut by size or meaning;
`Markdown`/`JSON`/`HTML` parsers by markup; the add-on `chonkie`, `slide` and `docling`
parsers are general or document-oriented). A `TextNode` already renders
`{metadata_str}\n\n{content}` with `{key}: {value}` per line, and
`excluded_embed_metadata_keys` keeps a field on the node but out of the embedded text. So this
story sets fields; it does not build a header string.

| node field | value | in the embedded text? |
|---|---|---|
| `text` | the messages, speaker lines included (the header is dropped: it is the channel line) | yes |
| `metadata.channel` | `Thread.channel.name`; left out when `unknown` | yes |
| `metadata.participants` | `Thread.participants`, joined with `, ` | yes |
| `metadata.doc_id` | the dsid | no |
| `metadata.channel_route` | `line1` / `export_path` / `unknown`, for SLACK-12's split | no |
| `metadata.first_turn`, `last_turn` | `0` and the last turn; SLACK-10 narrows them on a split | no |
| source relationship | the Document the node came from | not text |

The tension to manage: a header helps the vector carry channel and participants, but an
identical prefix on every chunk pushes 285,605 vectors toward each other. Only the two keys
that carry meaning are embedded.

**What a preview run showed** (throwaway code, NovaCare, LlamaIndex 0.14.24): the wrapper works
inside `IngestionPipeline`, and three things must be handled here or in SLACK-11:
1. The node must link to its source Document, or the docstore cannot upsert it on a re-run.
2. `SimpleDirectoryReader` adds `creation_date`, `last_modified_date`, `file_path`,
   `file_size`, `file_type` to the Document. They are copied to nodes and would land in the
   embedded text as an invented date. SLACK-11 loads with
   `file_metadata=lambda path: {"file_name": Path(path).name}`, verified to keep only the name;
   this story still excludes anything it did not set.
3. The Document id is a random UUID by default (see SLACK-11).

### Acceptance Criteria

```gherkin
Scenario: one thread, one node
  Given the NovaCare Document
  When SlackThreadParser runs inside an IngestionPipeline
  Then it returns one TextNode whose embedded text starts
       "channel: customer-success\nparticipants: Aisha, Priya, Ben, Tom, questionnaire-bot\n\n"
  And doc_id, channel_route, first_turn and last_turn are on the node but not in that text
  And the node's source relationship is the Document

Scenario: an unknown channel contributes nothing to the text
  Given a thread whose channel is unknown
  Then "unknown" does not appear in the embedded text

Scenario: no date anywhere
  Then no timestamp appears in the node metadata or the embedded text

Scenario: a thread with no speaker line
  Then it still becomes one node holding its text, with no participants
```

### Example with real data

`get_content(MetadataMode.EMBED)` for NovaCare, from the preview run:

```text
channel: customer-success
participants: Aisha, Priya, Ben, Tom, questionnaire-bot

Aisha (CS): Hey team — NovaCare sent an updated vendor risk assessment and DPA follow-up.
Can someone pick this up? Link: https://files.redwoodinternal/vra/novacare_2026.pdf :eyes:
...
```

2,256 characters, 16 messages, one node.

### Non-functional Requirements

Shared list, and NFR-7: the rendering and the pipeline plumbing are the library's.

### Dependencies

APIs data contracts: SLACK-8 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-10  `SlackMessageChunker`: split over-budget threads between messages ⬜

**Status** To do
**As a** retrieval index whose unit is the conversation
**I want to** a node over the token ceiling split into nodes on message boundaries
**So that** ~99% of threads reach the embedder whole and no message is cut in half

A second custom `NodeParser` (or `TransformComponent`), placed after `SlackThreadParser` in the
pipeline. A node under the ceiling passes through untouched; an over-budget node is cut
between messages, never inside one. `SentenceSplitter` alone does not do this: it cuts by
size wherever the size runs out.

Measured by the design: thread tokens are p50 821, p90 1,256, p99 1,725, max 3,101. At a
2,048-token ceiling about 99% of threads never split. Re-measure with the embedding model's
own tokenizer when it is chosen.

### Acceptance Criteria

```gherkin
Scenario: a normal thread passes through
  Given the NovaCare node, about 780 tokens, and a ceiling of 2,048
  Then the chunker returns the same node unchanged

Scenario: an over-budget thread splits on a message boundary
  Given a thread of 3,101 tokens and a ceiling of 2,048
  Then it becomes 2 nodes, each with its own first_turn and last_turn
  And no message is cut in half
  And every message lands in exactly one node
  And both keep the thread's channel, participants and doc_id

Scenario: ids are stable
  Then a node id is sha256(doc_id:first_turn:last_turn) and does not change between runs
```

A single message longer than the ceiling, if any exists, is the one place `SentenceSplitter`
is allowed; count them first.

### Non-functional Requirements

Shared list.

### Dependencies

APIs data contracts: SLACK-9 · Service Bus: N/A · Database: N/A · UI: N/A

---

## SLACK-11  The ingestion run: reader, pipeline, stores, hybrid retrieval ⬜  *(module-level; split when we reach it)*

All library code, wired together:

```text
SimpleDirectoryReader(data/slack/clean, file_metadata=name only)
  -> Document per thread, id = the dsid
  -> IngestionPipeline(transformations=[SlackThreadParser(), SlackMessageChunker(), embed_model],
                       docstore=..., vector_store=..., cache=IngestionCache)
  -> vector index  +  BM25Retriever over the same nodes  ->  QueryFusionRetriever
```

- **Reader.** `SimpleDirectoryReader` reads the clean `.txt` files as they are; no loader of
  our own. `file_metadata` keeps only `file_name` (verified: no dates reach the Document).
- **Document id = the dsid.** `filename_as_id=True` gives the full file path, which changes with
  the checkout location, so the id is set to the dsid after loading. The docstore upserts on
  it, so a re-run updates a thread's nodes instead of duplicating them.
- **Cache.** `IngestionCache` + `pipeline.persist()` skip node/transformation pairs already done.
- **BM25 is required, not optional.** 72.8% of threads carry an exact-match token —
  `r_9f8e7d6c`, `OF-ACME-001`, `Photon9B-int4` — that dense retrieval alone loses. 56.2% carry
  a URL and 72.8% a fenced code block, which push the same way.
- **No date** on any node (design section 5).
- Channel is also an authority signal available for free: `postmortems` and `incidents` are
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

**Does a missing channel hurt retrieval?** (from SLACK-5) 9,053 threads (3.2%) have channel
`unknown`, and nothing in them says where they came from. Report recall@20 separately for
questions whose gold thread has a channel and for questions whose gold thread is `unknown`:

| gold thread's channel route | questions | recall@20 |
|---|---|---|
| `line1` or `export_path` | … | … |
| `unknown` | … | … |

If the two rates are about the same, the missing channel does not matter. If `unknown` is
clearly lower, the channel line is helping search, and recovering more channels (for
example from the thread's content) becomes worth a story. Two rules follow for SLACK-9 and
here: every node carries `channel_route` in its metadata (kept out of the embedded text), so
this split is one group-by; and channel authority is a soft boost, never a filter, so an
`unknown` thread is never dropped from results.

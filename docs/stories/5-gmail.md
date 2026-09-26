# Gmail stories

The Gmail source of the pipeline: 121,390 thread exports → clean text → 578,254 message
records → LlamaIndex nodes → hybrid retrieval scored at thread level. Design and
evidence: [Gmail system design](../design/3-gmail-system-design.md).

Shared rules, the story template and the glossary are in [stories.md](../stories.md);
every story here follows them. Two rules deserve repeating because this stage leans on
library code harder than Confluence did:

1. **Library first.** LlamaIndex has no email or thread parser, so the message split is
   ours. Everything after it — context injection, splitting the long tail, dedup,
   caching, fusion, reranking — is library code we configure, not code we write. Design
   §6.1 lists the division.
2. **Nothing is dropped silently.** Counts reconcile at every stage. The 189 threads with
   no `From:` and the 13 partially-escaped threads are handled explicitly, not lost.

## Glossary (Gmail terms; the shared glossary is in stories.md)

- **Thread**: one exported `.txt` under `data/gmail/raw/`, one email conversation, named
  `dsid_<32 hex>__<YYYYMMDD>-<slug>.txt`. 121,390 of them.
- **`dsid`**: the 32-hex id in the filename. **The benchmark's unit of truth** —
  `expected_doc_ids` in `questions.jsonl` are `dsid`s, so every chunk must carry one.
- **Message**: one `From:` block inside a thread and the body under it. 578,254 of them,
  median 5 per thread.
- **Thread title**: line 1 of the file. Always present; differs from any `Subject:` in
  65% of threads, so it is independent signal.
- **Partially escaped**: a thread where *some* messages are JSON-escaped and the rest are
  not, so `is_escaped` (a whole-file count comparison) says False. 13 files corpus-wide.
- **Quoted history**: an `On … wrote:` line and the `>`-prefixed text under it, repeating
  a message that is already indexed on its own. 61,922 threads, 42.8 M chars.
- **Message record**: the ten derivable fields of one message (design §3), the unit
  written to `data/gmail/messages/` and handed to LlamaIndex as one `Document`.

## Module layout

```
tools/
    gmail_profile.py  GMAIL-0    profile: counts only, no rules
pipeline/gmail/
    cleaning.py    GMAIL-1a,1b clean_thread
    messages.py    GMAIL-3        split_messages
    attachments.py GMAIL-7    attachment_names
    quotes.py      GMAIL-6    strip_quotes
    headers.py     GMAIL-4    parse_headers
    dates.py       GMAIL-5    normalise_date
    records.py     GMAIL-8    MessageRecord, message_records
    corpus.py      GMAIL-2,9  write_clean_corpus, write_messages_corpus
    index.py       GMAIL-10,11,12  to_document, chunk_id, build_pipeline
    retrieve.py    GMAIL-13,14     ThreadRollup, build_retriever
    evaluate.py    GMAIL-15   recall_at_k
```

## Build order and one-liners

| # | Story | One line |
|---|---|---|
| 0 | GMAIL-0 profile | `tools/gmail_profile.py` counts files, bytes, tokens, escapes and missing `From:` from `raw/`; decides no rule |
| 1a | GMAIL-1a clean_thread | unescape the 27,870 flagged threads with `pipeline.cleaning`, then a whitespace-only tidy; **skip** `fix_structure`, which corrupts Gmail bullets |
| 1b | GMAIL-1b escape edge cases | the 179 threads `is_escaped` misses; a rule scored on a hand-labelled truth set |
| 2 | GMAIL-2 clean corpus | write `data/gmail/clean/` + manifest, one row per thread |
| 3 | GMAIL-3 split_messages | cut a clean thread on `From:` at line start; a thread with none is one message |
| 4 | GMAIL-4 parse_headers | `From`/`To`/`Cc`/`Date`/`Subject` out of one block, addresses split on commas |
| 5a | GMAIL-5a normalise_date (ISO, RFC 2822) | 568,479 dates to one UTC instant; the colon-offset trap; 126 stay unreadable |
| 5b | GMAIL-5b normalise_date (Gmail display) | 8,595 dates with named zones and a 12-hour clock |
| 6 | GMAIL-6 strip_quotes | drop the `On … wrote:` block and its `>` lines |
| 7a | GMAIL-7a attachments | file names on labelled lines; a value counts only where it holds file names |
| 7b | GMAIL-7b attachments | bracket lines and bullet lists below an empty label |
| 8 | GMAIL-8 message_records | assemble the ten fields per message, thread fields from the filename and line 1 |
| 8b | GMAIL-8b message truth set | 30-40 real messages with hand-checked output; every edge case found in stories 3-6 |
| 9 | GMAIL-9 messages corpus | write `data/gmail/messages/*.jsonl` + manifest; counts reconcile |
| 10 | GMAIL-10 to_document | one LlamaIndex `Document` per record; metadata templating does the context injection |
| 11 | GMAIL-11 chunk_id | deterministic `id_func` for the splitter |
| 12 | GMAIL-12 build_pipeline | `IngestionPipeline` with `SentenceSplitter`, docstore and cache |
| 13 | GMAIL-13 ThreadRollup | node postprocessor: chunks → distinct `dsid`s, best chunk wins, siblings for context |
| 14 | GMAIL-14 build_retriever | `QueryFusionRetriever` over vector + BM25, then a reranker |
| 15 | GMAIL-15 recall_at_k | score the 55 Gmail questions on `expected_doc_ids` |
| 16 | GMAIL-16 audit_gmail | every rule that can misfire as a corpus count with three real examples |
| 17 | GMAIL-17 run log | LlamaIndex instrumentation: progress, tokens, failures and retrieval traces to JSONL |

Stories 1–9 are pure and offline. 10–12 configure library code. 13–15 are the retrieval
side and depend on an embedded index existing. 16 and 17 are the observability pair and
can be built at any point after the stage they watch: GMAIL-16 after GMAIL-9, GMAIL-17
before the first full embed run, because it is what makes that run diagnosable.

---

## GMAIL-0  Corpus profile  ✅

**Status:** Done.

**As a** engineer about to write cleaning and parsing rules for 121,390 threads
**I want to** a single `profile.json` produced by committed code
**So that** no Gmail story quotes a number nobody can reproduce

`tools/gmail_profile.py`, the Gmail twin of `tools/slack_profile.py`. It only counts: it
changes no file and decides no rule. It reads `data/gmail/raw/` and writes
`data/gmail/profile.json` (gitignored like every generated corpus file); the numbers that
matter are pinned as a test instead (`test_real_corpus_counts`).

**Acceptance Criteria (Gherkin)**
- Given `data/gmail/raw/`, When `profile(raw_dir, out_path)` runs, Then `profile.json` holds `files`, `bytes`, `tokens` (4 chars per token, nearest-rank p50/p90/p99/max), `literal_escape_files`, `is_escaped_files`, `ambiguous_escape_files` and `no_from_files`
- Given a thread with a literal `\n` that `is_escaped` says is not escaped, Then it is counted as ambiguous, not judged: printf string versus partial damage is GMAIL-1b's rule
- Given a thread where `From:` appears only mid-sentence, Then it counts in `no_from_files`; a `From:` at the start of a line, real or escaped, does not
- Given a second run, Then the file is byte-identical

**Example with real data**
```json
{ "files": 121390, "bytes": 860188084,
  "tokens": { "p50": 1745, "p90": 2186, "p99": 2640, "max": 4313 },
  "literal_escape_files": 28049, "is_escaped_files": 27870,
  "ambiguous_escape_files": 179, "no_from_files": 189 }
```

What this settled, so later stories do not re-argue it:
- **28,049 is "has a literal `\n`", not "is escaped".** It splits into 27,870 that `is_escaped` flags and 179 that it does not (mostly real damage, not code, as GMAIL-1b measured). GMAIL-1 and GMAIL-2 originally said `was_escaped` is True on 28,049 rows, which counted threads that only mention `\n`. GMAIL-1a corrects it: `was_escaped` is True on 27,870.
- **189 needs a line-start test.** A plain "no `From:` anywhere" gives 183, because six threads mention `From:` in prose. `From:` counts only at the start of a line, real or escaped.
- **Not profiled here on purpose:** messages, message sizes, participants, quoted history, date formats. Each needs a rule that is not built yet (GMAIL-3, 4, 5, 6), so each is counted by the story that builds the rule. Running the tool replaces the earlier hand-made `profile.json`, which held those numbers without code behind them.

**Non-functional Requirements**
Shared rules apply. Reuses `pipeline.cleaning.is_escaped` unchanged. Pure counting over a
folder read in file-name order; about 8 seconds on a laptop.

**Dependencies** APIs data contracts: `pipeline.cleaning.is_escaped` · Service Bus: N/A ·
Database: N/A · UI: N/A

---

## GMAIL-1a  clean_thread: repair the fully escaped threads  ✅

**Status:** Done. Real corpus: 27,870 threads flagged, all 121,390 end with one newline, 0 new `#` lines. 11 escaped threads have no `From:` line after unescaping (not yet explained).

**Background**
27,870 of the 121,390 raw threads (23%) were saved as a JSON string: the line breaks are the
two characters `\` and `n`. `pipeline.cleaning` already detects and decodes exactly this for
Confluence (`is_escaped`, `unescape`), so this story reuses both unchanged. `ftfy` and
`json.loads` decode the same samples identically, so neither is added as a dependency.

The one thing that cannot be reused is `normalize`: it calls `fix_structure`, which rewrites
Confluence wiki markup and, on Gmail, turns a bullet such as `- draft_transfer_annex_notes.docx`
into `## - draft_transfer_annex_notes.docx`. Measured over the corpus it adds 27 false `#`
lines and changes 92 threads. Gmail gets its own whitespace-only tidy instead.

**Not in this story:** 179 threads contain a literal `\n` that `is_escaped` does not flag
(printf strings, JSON examples, and partly escaped threads). They come back unchanged here;
GMAIL-1b decides them.

**As a** pipeline developer
**I want to** turn one raw thread into clean text with real line breaks
**So that** `From:` is at the start of a line and every later story can rely on it

**Acceptance Criteria (Gherkin)**
- Given a raw thread `is_escaped` flags, When `clean_thread` runs, Then the text has real newlines and `was_escaped` is True
- Given a raw thread with no escapes, Then the text is unchanged apart from tidying and `was_escaped` is False
- Given a thread with one literal `\n` inside a `printf` string and nothing else escaped, Then the text is **not** unescaped
- Given any thread, Then no line gains a leading `#` and `fix_structure` is never called
- Given any thread, Then trailing spaces are removed, runs of blank lines become one, and the text ends with exactly one newline
- Given the same thread twice, Then the output is identical
- Given the whole corpus, Then 27,870 threads report `was_escaped` True and every clean thread ends with exactly one newline

**Example with real data**

`dsid_00ada6ccfbef490db1abe8e97b9bbf6e__2…` — why `fix_structure` is excluded:

```
line     '- draft_transfer_annex_notes.docx'        (a bullet in an attachment list)
would be '## - draft_transfer_annex_notes.docx'     (a heading, wrong)
```

**Non-functional Requirements**
Shared rules apply. Pure: string in, `CleanResult` out, no disk. Reuses `is_escaped`,
`unescape` and `CleanResult` from `pipeline.cleaning`; the only new code is the tidy.
*Observability:* `was_escaped` goes in the manifest row (GMAIL-2), so the 27,870 is countable.

**Dependencies** APIs data contracts: `pipeline.cleaning.is_escaped`, `.unescape`,
`.CleanResult` · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-1b  Escape edge cases: the 179 threads `is_escaped` misses  ⬜

**Status:** To do. Needs a decision recorded here before code.

**Background**
179 threads hold a literal `\n` but `is_escaped` says no. Reading them, most are real
damage, not code: 379 of 523 occurrences are prose (`Subject: …\n`, `…close: \n- Confirm…`), only
about 107 are code (`"\n\n--END--"`, `\r\n` HTTP examples). The earlier count of 166 code and 13
partial threads was wrong. The design's `28,049` is "has a literal `\n`", not "is escaped".

A rule was scored on 40 hand-labelled occurrences
(`tests/fixtures/gmail_escape/expected.json`): decode a `\n` unless it follows `\r` or sits
inside a quoted span of 40 characters or fewer. It gets 38 of 40. The two misses are a
single-quoted JavaScript string and a quoted message snippet. Measured on the truth set only, so
it is a fit, not an independent test.

**Open:** whether to use that rule, what `was_escaped` means for a partly repaired thread, and
what to do with the 37 double-escaped `\\n`. Decided when this story starts.

**Found while building GMAIL-5a:** a literal `\r` (backslash and `r`, not a carriage return) survives `clean_thread`. Measured after `parse_headers`: 126 senders, 126 subjects, 125 recipient lists, 126 dates and 143 bodies carry it, for example the subject `procurement — DPA, SOC 2 & PO workflow\r`. `\r` is not decoded because the current rule treats it as a code-example case. GMAIL-5a strips it from the date only, as a stop-gap; the fix belongs here, in `clean_thread`, after which that stop-gap can go.

---

## GMAIL-2  Clean corpus: data/gmail/clean/ and its manifest  ✅

**Status:** Done. Real corpus: 121,390 files written, 27,870 escaped, 0 files whose bytes differ from their manifest hash, 57 seconds, manifest 45 MB. Simple writer chosen: no failure handling or folder swap, because the data has no duplicate names, empty files or undecodable files. Add them if a later run needs them.

**Background**
Same shape as `write_clean_corpus` for Confluence: read `raw/`, write `clean/`, one
manifest row per thread. The manifest is the audit trail and the input to every count
reconciliation later.

**As a** pipeline developer
**I want to** write one clean file per raw thread with a manifest row
**So that** stage 2 reads a folder it can trust, and any byte change is provable

**Acceptance Criteria (Gherkin)**
- Given `data/gmail/raw/`, When the writer runs, Then `data/gmail/clean/` holds 121,390 `.txt` files with the same names
- Given each file, Then `_manifest.json` has a row with `file`, `raw_sha256`, `clean_sha256`, `was_escaped`, `raw_lines`, `clean_lines`, `raw_bytes`, `clean_bytes`
- Given the manifest, Then rows are in file-name order and `was_escaped` is True on exactly 27,870 rows
- Given a second run, Then every `clean_sha256` is identical
- Given the writer, Then it never writes into `raw/`

**Example with real data**
```json
{"file": "dsid_000025680c494c78b8005828c90c9293__20260625-payment-orchestration-costpool-choreography.txt",
 "raw_sha256": "…", "clean_sha256": "…", "was_escaped": false,
 "raw_lines": 150, "clean_lines": 149, "raw_bytes": 9336, "clean_bytes": 9336}
```

**Non-functional Requirements**
Shared rules apply. Reuses `pipeline.manifest.manifest_row` unchanged; does not import `pipeline.corpus` (it pulls in the Confluence Markdown parser). Reads raw files as bytes because 69 threads hold a real `\r`. Golden:
`tests/golden/gmail_clean_fingerprint.json`, one sha256 over every row's `clean_sha256`
in manifest order.

*Maintainability:* `manifest_row` is reused unchanged; if Gmail needs a field Confluence
does not have, it goes in a Gmail-only row builder beside it, never as a branch inside it.
*Observability:* the manifest is the audit trail — `was_escaped` count, byte and line
deltas per file. A run prints one summary line: files in, files out, escaped, bytes.

**Dependencies** APIs data contracts: GMAIL-1a, `pipeline.manifest.manifest_row` ·
Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-3  split_messages: cut a thread into messages  ✅

**Status:** Done. Real corpus: 578,254 blocks start with `From:`, 189 threads give one whole-body block (578,443 blocks in all), 609 threads have a preamble, 0 non-blank lines lost. Signature is `(title, preamble, blocks)`: option A chosen, a plain cut that keeps everything. The Date-before-From and marker cases go to GMAIL-3b.

**Background**
The only structural signal in this corpus. 92 threads of 121,390 contain a Markdown
heading, so there are no sections; the author's unit is the message and its boundary is
`From:` at the start of a line. 189 threads have no `From:` anywhere — they are real
threads written as one body under the title, and they must still reach the index or
their `dsid` is unreachable.

**As a** pipeline developer
**I want to** split one clean thread into its message blocks
**So that** each message can become its own embedded unit

**Acceptance Criteria (Gherkin)**
- Given a clean thread, When `split_messages` runs, Then it returns `(title, preamble, blocks)` where `title` is line 1, `preamble` is the text between the title and the first `From:`, and each block starts with `From:` at a line start
- Given a thread with 5 `From:` lines, Then 5 blocks are returned, and the title, preamble and blocks together hold every non-blank line of the file
- Given a `From:` inside a quoted block or mid-line, Then it does **not** start a new block
- Given one of the 189 threads with no `From:`, Then one block is returned holding the whole body, and the caller can tell it apart (no headers parse)
- Given the corpus, Then 578,254 blocks start with `From:`, plus 189 whole-body blocks, 578,443 in all

**Example with real data**

`dsid_0070cd596374404085ed0cbca4e3a9e2__20280316-renewal-paperwork…` — one of the 189:

```
line 1  'Re: Renewal paperwork — MSA + order form edits for capacity uplift'
line 3  'Hi Nikhil,'
…       no From:/To:/Date: anywhere
→       title = line 1, one block = lines 3..end, headers empty
```

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus. No regex over the whole file body where a line scan will do.

*Maintainability:* the boundary rule lives in exactly one function; nothing else in the
codebase is allowed to look for `From:`.
*Observability:* returns the block count per thread for GMAIL-9's reconciliation. Audit
rows: `no_from_thread` (expect 189) and `from_in_quote` (expect 0 new blocks).

**Dependencies** APIs data contracts: GMAIL-1a · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-3b  Lines that a plain cut leaves in the wrong block  ⬜

**Status:** To do. Sized after GMAIL-4 and GMAIL-5, which show how much it matters.

A plain cut at `From:` (GMAIL-3) leaves three real cases as they are, measured on the clean threads:
- **`Date:` or `Sent:` on the line just before `From:`:** 826 blocks in 181 threads. The date sits in the preamble or the previous block, so GMAIL-4 finds no `Date` for that email.
- **A marker such as `---Message 2/4---` just before a `From:`:** 731 blocks in 199 threads. The marker ends up at the end of the previous block.
- **Preamble text:** 609 threads: 173 a `Date:` line, 181 a marker, 269 other text such as a one-paragraph summary. GMAIL-3 keeps all of it in `preamble`.

---

## GMAIL-4  parse_headers: the five fields of one block  ✅

**Status:** Done. `pipeline/gmail/headers.py`, 24 tests. Over all 578,443 blocks: 189 have no headers (every field empty), 577,200 have a date (574,496 `Date:` plus 2,704 `Sent:`).

**Background**
Measured on the 578,255 blocks that have header lines:
- The order `From → To → [Cc] → Date → Subject` holds in **98.5%** (569,509). The design doc said 99.6%. The next most common order puts `Date` and `Subject` before `To` (3,433 blocks). Order does not matter to the rule: every field is found wherever it sits.
- `Cc` is absent in **21.6%** (125,155), not 19%.
- `Bcc` appears in **500** blocks (not 79), `Reply-To` in 3 (not 2). Both are ignored. `References` (story said 56) was not re-counted.
- **2,704 blocks use `Sent:` instead of `Date:`**, and none has both. Not in the original story.
- **1,331 blocks have an `Attachments:` line right after `Subject:`**. So only known header names count as headers; anything else ends the header lines and stays in the body for GMAIL-7.
- 418 blocks have no blank line after the headers. Counting the 189 with no headers, 1,157 blocks end with no `To`, 445 with no `Subject`.
- Long recipient lists sometimes wrap onto a second line (about 17 fields). Python's `email.parser.HeaderParser` handles that but drops the first body line when there is no blank line (31 blocks, e.g. `[attachment: cloudledger_registrants_0621.csv]`), so it was not used. The rule joins wrapped lines itself.
- Comma names such as `Ruiz, Elena <a@b>`: 138 pieces; `(none)`, `none` and `;` lists: 2,801 pieces with no address.

**As a** pipeline developer
**I want to** read the header lines of one message block into a typed record
**So that** sender, recipients, date and subject are metadata rather than text

**Acceptance Criteria (Gherkin)**
- Given a block, When `parse_headers` runs, Then it returns `from_`, `to`, `cc`, `date_raw`, `subject` and the body with the header lines removed
- Given `To: A <a@x>, B <b@y>`, Then `to == ["A <a@x>", "B <b@y>"]`, split on commas outside angle brackets
- Given `To: Ruiz, Elena <e@x>`, Then `to == ["Ruiz", "Elena <e@x>"]`: the fragment without an address stays as a name only, nothing is invented or lost. `from_` is never split
- Given `(none)` or `Ana; Raj`, Then it is kept as one raw entry; a trailing comma leaves no empty entry
- Given a header line wrapped onto an indented next line, Then the two are joined
- Given a block with no `Cc:`, Then `cc == []`
- Given a block with `Sent:` and no `Date:`, Then `date_raw` is the `Sent:` value; if both exist, `Date:` wins
- Given `Bcc`, `Reply-To` or `References`, Then the line is removed from the body and not returned
- Given a line such as `Attachments: plan.pdf` after `Subject:`, Then it stays in the body
- Given a block whose headers are out of order, Then all five are still found
- Given a block with no headers (GMAIL-3's 189), Then all fields are empty and the body is the whole block

**Example with real data**
```
From: Vivek Kulkarni <vivek.kulkarni@redwood.ai>
To: Amal Khan <amal.khan@greenlinehealth.com>
Cc: Kimberly Park <kimberly_park@redwood.ai>, Marissa Cole <marissa_cole@redwood.ai>
Date: Thu, 25 Jun 2026 11:05:00 -07:00
Subject: Re: Invoice & VAT approach for multi-entity pilot (Greenline)
-> from_='Vivek Kulkarni <vivek.kulkarni@redwood.ai>'
   to=['Amal Khan <amal.khan@greenlinehealth.com>']
   cc=['Kimberly Park <kimberly_park@redwood.ai>', 'Marissa Cole <marissa_cole@redwood.ai>']
   date_raw='Thu, 25 Jun 2026 11:05:00 -07:00'
   subject='Re: Invoice & VAT approach for multi-entity pilot (Greenline)'
```

**Non-functional Requirements**
Shared rules apply. Pure, no state. Never parses the date: `date_raw` is GMAIL-5's input, and the `Sent:` style (`Thu, Apr 24, 2025 9:12 AM`) is GMAIL-5's to read.

*Maintainability:* the header names live in two constants (`USED_KEYS`, `IGNORED_KEYS`), so handling `Bcc` later is a one-line change with a test.
*Observability:* audit row `header_order` counts blocks whose order is not the 98.5% shape, and `header_missing_field` counts blocks short a field, both with three real examples.

**Dependencies** APIs data contracts: GMAIL-3 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-5a  normalise_date: the ISO and RFC 2822 dates  ✅

**Status:** Done. `pipeline/gmail/dates.py`, 18 tests. Of 577,200 dates: 414,691 read by the RFC 2822 rule, 153,788 by the ISO rule, 8,721 left for GMAIL-5b (8,595) or unreadable (126).

**Background**
Measured over every date `parse_headers` returns (`Date:` plus 2,704 `Sent:`), the standard library is right on 454,737 of 577,200 (78.8%), not the 98.21% the first draft of this story claimed. That figure counted **111,029 colon-offset dates** (`Thu, 25 Jun 2026 11:05:00 -07:00`) as parsed, but `parsedate_to_datetime` silently drops their zone and returns a wrong, zone-less time. It also reads `Mon, Apr 28, 2025 4:40 PM` as 04:40, silently dropping the PM (handled in GMAIL-5b). The space form `2026-09-17 09:12 -0400` needs no rule of its own: `fromisoformat` reads it on Python 3.11+.

**As a** pipeline developer
**I want to** turn an ISO or RFC 2822 `Date:` text into one UTC instant, the sender's offset and an assumed flag
**So that** every message can be sorted and filtered on one clock, and its local time rebuilt

**What is returned** (`NormalisedDate`)

| Field | Meaning |
|---|---|
| `sent_at` | The instant on the UTC clock, `2026-06-25T16:12:00+00:00` |
| `utc_offset_minutes` | How far the sender's clock was from UTC, `-420` for `-0700`; empty when the text gave no zone, and for `-0000` (UTC, sender zone unknown) |
| `assumed_utc` | True only when the text had no zone and UTC was assumed; `-0000` is not an assumption |
| `rule` | `iso` or `rfc2822` (`loose` in GMAIL-5b) |

Later stories store `sent_at` for sorting and filtering, and `sent_at` as whole seconds (`sent_at_ts`) when indexing, because many vector stores only range-filter on numbers. The original `date_raw` is kept beside them.

**Acceptance Criteria (Gherkin)**
- Given `2026-06-25T09:12:00-07:00`, Then `sent_at` is `2026-06-25T16:12:00+00:00`, the offset is `-420`, `assumed_utc` is false
- Given `Thu, 25 Jun 2026 09:12:00 -0700`, Then the result is the same instant
- Given `Thu, 25 Jun 2026 11:05:00 -07:00` (colon in the offset), Then it is `2026-06-25T18:05:00+00:00`, not the zone-less 11:05
- Given `2026-09-17 09:12 -0400`, Then it parses (space form, no seconds)
- Given a date with no zone such as `2027-04-03 09:12`, Then it is read as UTC and `assumed_utc` is true
- Given `-0000`, Then it is UTC, the offset is empty and `assumed_utc` is false
- Given a trailing `(PST)` comment or a literal `\r`, Then it is ignored
- Given an unparseable value, a bare date with no time of day, or a day that does not exist (`29 Feb 2027`), Then it raises `ValueError` naming the date; it never returns a default

**Measured on the real corpus (577,200 dates)**
- RFC 2822 rule 414,691 · ISO rule 153,788 · `assumed_utc` 226 · offset unknown 3,048 (226 plus 2,822 `-0000`)
- 8,721 raise here: the 8,595 that GMAIL-5b reads, plus **126 that stay unreadable** (about 44 rare shapes, 12 bare dates such as `2027-03-18`, 14 days that do not exist). The first draft said all dates parse; 126 (0.02%) will not. GMAIL-8 already falls back to the date in the file name when a message has no readable date.

**Found in review, not fixed here:** a literal `\r` also sits in 126 senders, 126 subjects, 125 recipient lists and 143 bodies (cleaning residue). This story only strips it from the date; the root cause belongs to GMAIL-1b (`clean_thread`).

**Non-functional Requirements**
Shared rules apply. Pure, offline, standard library only.

*Maintainability:* one function per rule, each returning a result or `None`, tried in order.
*Observability:* the result carries which rule read it and `assumed_utc`. Audit row `date_rule` reports the split and the unreadable count.

**Dependencies** APIs data contracts: GMAIL-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-5b  normalise_date: Gmail display dates and named zones  ✅

**Status:** Done. `pipeline/gmail/dates.py` `loose` rule, 36 tests in total for GMAIL-5. Real corpus: 8,595 read by `loose`; 126 dates (0.02%) still raise; `assumed_utc` 3,010 in all (226 ISO plus 2,784 display-style); offset unknown 5,832 (3,010 plus 2,822 `-0000`). Built on GMAIL-5a. The 8,595 are in Gmail's display style (`Thu, May 20, 2027 at 09:12 AM PDT`, `2026-11-15 13:12 UTC`, `Fri, 25 Sep 2026 at 16:12`).

Adds a third rule `loose` to `normalise_date`:
- **Named zones** from one written table (PDT, PST, EDT, EST, CDT, CET, CEST, GMT, UTC, SGT, JST; BST read as British and IST as India, 20 blocks); `PT` and `ET` switch between summer and winter by the date (needs the `tzdata` package).
- **12-hour clock**: `4:40 PM` is 16:40 (the standard library silently drops the PM); a stray PM on a 24-hour time (`13:56 PM`, `00:30 PM`) is ignored.
- **No zone** (about 2,784 dates): read as UTC with `assumed_utc` true.
- Full weekday and month names, `Sept`, a missing comma after the day; misspelled month or weekday names (`Marxxx`, `Foo`) raise, found in review. Month and weekday names come from a written table, so the standard library's locale is never involved.
- 12 bare dates such as `2027-03-18` are no longer read as midnight UTC (the ISO rule now needs a time of day, found in review); with 14 impossible days and rare shapes that makes the 126 unreadable.

Decisions already made: no zone means UTC plus the flag; `-0000` is UTC without the flag; one written zone table rather than `dateutil` (which can ignore an unknown zone name silently).

---

## GMAIL-6  strip_quotes: remove what is already indexed  ✅

**Status:** Done. `pipeline/gmail/quotes.py`, 31 tests. Over all 578,443 message bodies: 120,288 change, 780 become empty (723 more were already empty, headers only), 1,505 keep an `On … wrote:` line with no quote after it (flagged), 45,457,656 characters removed.

**Background**
A reply quotes the earlier message back, and every word of that copy is normally already embedded on the message it came from. Leaving it in means a question matches the original and every reply that quoted it. Measured on the real bodies (not re-checking the first draft's "61,922 threads"):
- **120,151 bodies (20.8%) have `>` lines**, holding 38,379,270 characters (5.6% of all body text). The first draft said 42.8 M characters (6.3%); that could not be reproduced. With the removed `On … wrote:` lines the total is 45.5 M.
- **The first draft's rule was wrong.** It said to cut from `On … wrote:` to the end of the body. That deletes the reply whenever the quote comes first: in 9,108 bodies the quote is at the top with the answer below it, in 19,961 the author wrote text on both sides of it, and in 1,396 the answers sit between quoted lines. The rule removes only the quoted lines and their opener, and keeps every other line.
- **The premise "already embedded" is mostly true:** of 98,344 quotes that could be checked, 82.0% (80,647) are copies of an earlier message in the same thread. The rest are often placeholders such as `> [original message quoted]`, or quote a message that is not in the thread. They are removed anyway; the clean file on disk keeps them.
- **The `email-reply-parser` library was tried and not adopted.** It agrees with the simple rule on 83,880 of 120,151 quoted bodies, but it also strips signatures (over 20% more text in 601 bodies, and it empties 29 bodies the simple rule keeps, text after `---`) and it crashed on 2 real bodies (a regex "bad escape"). GMAIL-7 needs the attachment lines it may cut.

**As a** pipeline developer
**I want to** remove the quoted earlier email from one message body
**So that** each message embeds only what its author wrote

**Acceptance Criteria (Gherkin)**
- Given a line that starts with `>` (any depth: `>>`, `> >`, no space as in `>Jordan`), Then it is removed
- Given an `On … wrote:` line directly above quoted lines (or one blank line above them), Then it is removed with them; both shapes are covered: `On Mon, May 10, 2027 at 08:23 Naomi Feldman <naomi@…> wrote:` and `On 2026-09-05 10:12, Claire Dawson wrote:`
- Given an opener that ends in a leftover literal `\r` or a short bracketed note, Then it is still an opener; an opener with the quote on the same line (`… wrote: > text`) is removed whole
- Given a quote at the top with the answer below it, or author text on both sides, or answers between quoted lines, Then all of the author's text is kept
- Given a forwarded message (`--- Forwarded message ---`, `-----Original Message-----`) or quoted history with no `>` marks (inline `From:`/`Sent:` lines), Then it is kept: it cannot be told from new text
- Given an `On … wrote:` line with no quote after it, Then it is kept and `opener_unmatched` is true
- Given lines that only look like openers (`On quoting: …`, `… wrote to execs: …`, `… wrote:"`), Then they are kept
- Given a body with no quoting, Then it is returned unchanged; the remaining text is always tidied (trailing spaces, runs of blank lines)
- Given a body that is only a quote, Then the text is empty (GMAIL-8 sets the `body_empty` flag)
- Given a second run on its own output, Then nothing changes

**Example with real data**

`dsid_0003343918ed4f56960a7d38b9848893`, reply 2 (quote first, answer below):

```
before  'On 2026-09-05 10:12, Claire Dawson wrote:'
        '> Thanks for the walkthrough earlier. We captured our prioritized constraints in ...'
        '> 1) Licensing model for edge nodes...'
        ''
        'Hi Claire — appreciate the details and the PDF. High level answers below ...'

after   'Hi Claire — appreciate the details and the PDF. High level answers below ...'
        quoted_chars=359  opener_unmatched=False
```

**Returned** (`StrippedBody`): `text`, `quoted_chars` (every removed character, one newline per removed line) and `opener_unmatched`.

**Non-functional Requirements**
Shared rules apply. Pure, standard library plus the shared whitespace tidy from `pipeline.gmail.cleaning`. The quote stays in the clean file on disk; only the returned text loses it, so nothing is destroyed.

*Maintainability:* the two patterns (`OPENER`, `QUOTE_ON_OPENER_LINE`) are named constants with real examples above.
*Observability:* `quoted_chars` per message, summing to 45,457,656. Audit rows `quote_opener_unmatched` (1,505 bodies) and `body_empty` (780) list real examples; both must stay small.

**Known limits (measured, left for later):** 1,505 bodies keep an unmarked quoted history (kept and counted); a forward is kept even where it repeats an earlier message; 91 bodies have nested quotes that are removed along with the rest.

**Review notes:** a code review found openers ending in a literal `\r` or a note, and openers with the quote on the same line (602 lines), missed by the first version; fixed here. The literal `\r` itself is cleaning residue owned by GMAIL-1b.

**Dependencies** APIs data contracts: GMAIL-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-7a  attachments: file names on labelled lines  ✅

**Status:** Done. `pipeline/gmail/attachments.py`, 32 tests. Over all 578,443 message bodies (read after `strip_quotes`): 273,086 labelled lines, 231,421 messages with at least one file name, 347,011 names, 24,873 labelled lines with no name (prose, `none`, promises). The bracket form and the bullet lists are GMAIL-7b.

**Background**
The first draft said `Attached:` is usually a sentence and must be skipped. **That was wrong.** Of 17,145 `Attached:` lines, 15,223 (88.8%) hold a file name; only 1,752 are prose such as `Attached: sample invoice mock (internal) and entity mapping template.` So the rule does not skip a label; it accepts a value only where it finds file names. Measured on the real lines:

| Label | Lines | With a file name on the line |
|---|---:|---:|
| `Attachments:` | 148,567 | 134,208 |
| `Attachment:` | 85,351 | 79,319 |
| `Attached:` | 17,145 | 15,223 |
| `Attachments referenced:` | 7,659 | 6,809 |
| `Attachment stubs:` / `stub:` | 5,250 | 4,384 |
| `Attachments included:` | 3,538 | 3,033 |
| `Attachment(s):` | 1,413 | 1,195 |

Case does not matter (260,400 capitalised, 11,437 lowercase, 79 all capitals), and a bullet before the label (2,793 lines) is allowed. The first draft's "110,768 threads" was not reproduced: about 118,000 threads have a label under a looser set of spellings.

What is and is not a file name (each found by measuring, each has a test):
- **Shape, not a fixed list:** a word with a dot and a 2 to 8 character extension that starts with a letter. A list of extensions would miss `.gdoc` (223), `.vcf` (115), `.gslides` (85), `.js` (80), `.url` (67), `.sig` (55) and more. Starting the extension with a letter rejects sizes (`1.2MB`, 3,309 tokens), versions (`v1.2`, `TLS1.3`) and `e.g.`.
- **Rejected:** MIME types (`application/vnd…sheet`, 18,350), email addresses, domains (`.com .net .org .io .co …`), and a type written in capitals inside brackets (`(TAR.GZ, 18MB)`, 7).
- **Path or link:** the last segment is the name (`Diva/Diva-crossconnect.pdf`, 127 such tokens).
- **A sentence around a name:** only the space-free word that ends in an extension is kept, so a sentence never enters the field. A name with real spaces (`Q3 Report.pdf`) is cut to `Report.pdf`; a known limit, at most a few hundred of 821 cases, most of which are sentences.
- **Repeats:** 4,713 messages list the same name twice; one copy is kept, in first-seen order. Names that differ only in case stay separate.

**As a** pipeline developer
**I want to** pull attachment file names out of a message
**So that** attachments are filterable metadata instead of body text

**Acceptance Criteria (Gherkin)**
- Given `Attachment: Greenline_PO_3042.pdf (application/pdf)`, Then `["Greenline_PO_3042.pdf"]`
- Given `Attachments: entity_mapping_template.xlsx, Greenline_SOW_v2.docx`, Then both names, in order
- Given a label in any case, with a bullet or indent before it, and the labels `Attachment(s)`, `Attached`, `Attachments referenced`, `Attachments included`, `Attachment stub(s)`, Then it is read
- Given `Attached: sample invoice mock (internal) and entity mapping template.`, `none`, `(will attach)` or `detailed-sizing-spreadsheet (to be uploaded)`, Then `[]`
- Given `Novus-VPC-Requirements.pdf (1.2MB)` or a MIME type in brackets, Then only the file name is returned
- Given semicolons, the word `and`, square brackets, a name inside round brackets, or trailing punctuation, Then the names are still found
- Given a line that does not start with the label (a sentence, a `>` quote, `Attaching:`, `Attachments in thread:`, a bracket line, or bullet lines below an empty label), Then it is not read
- Given a name listed twice, Then it appears once; given no label, Then `[]`

**Example with real data**
```
'Attachment: Greenline_PO_3042.pdf (application/pdf)'                 -> ['Greenline_PO_3042.pdf']
'Attachments: entity_mapping_template.xlsx, Greenline_SOW_v2.docx'    -> ['entity_mapping_template.xlsx', 'Greenline_SOW_v2.docx']
'Attachments: MAP-template-v1.gdoc (link), MAP-slate-v1.gslides (link)' -> ['MAP-template-v1.gdoc', 'MAP-slate-v1.gslides']
'Attached: sample invoice mock (internal) and entity mapping template.' -> []
```

**Decisions:** read the text after `strip_quotes` (7,724 attachment lines sit inside quotes and would be counted twice); a shape rule, not a list of extensions; sentence text never enters the field; split the story so this PR stays small.

**Non-functional Requirements**
Shared rules apply. Pure, standard library only.

*Maintainability:* the label pattern, the separators, the MIME prefixes and the domain endings are named constants at the top of the module.
*Observability:* audit row `attachment_unread_lines` counts labelled lines with no file name (24,873) and lines that name attachments in a form 7a does not read (`Attaching:` 3,633 lines, other labels), each with three real examples.

**Dependencies** APIs data contracts: GMAIL-6 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-7b  attachments: bracket lines and bullet lists  ⬜

**Status:** To do. Built on GMAIL-7a.

Two more forms carry the same information and are not read by 7a (measured over all bodies, text after `strip_quotes`):
- **Bracket lines, one file per line:** `[Attachment: Helios_MSA_redline.docx (docx - redline)]`, 55,774 lines. Includes `[Attachment: none]` and `[Attachment stubs included above]`.
- **Names on bullet lines below an empty label:** `Attachments:` then `- SustainCo_Scorecard.xlsx (xlsx)`, 5,781 label lines (4,315 under `Attachments:`).
- **`Attaching:` lines** (3,633) hold the name inside a sentence (`Attaching: initial procurement checklist we use (Procurement_requirements.xlsx).`); decide here whether to read them.

Reuses `file_name_of` from 7a for what counts as a name. Same edge-case discipline: inventory the real lines first, then the tests.

---

## GMAIL-8  message_records: the ten fields  ⬜

**Status:** To do.

**Background**
Assembles GMAIL-3 to 7 into the record that becomes one LlamaIndex `Document`. Ten
fields, all provable from the bytes (design §3). Provider metadata does not exist here —
across 20,000 threads: `Message-ID` 1, `In-Reply-To` 1, `Labels` 1 — so nothing is
invented to fill a schema.

**As a** pipeline developer
**I want to** turn one clean thread into its message records
**So that** stage 3 has flat, typed rows and never re-parses text

**Acceptance Criteria (Gherkin)**
- Given a clean thread and its filename, Then one `MessageRecord` per block is returned with `dsid`, `thread_title`, `thread_date`, `message_index`, `sender`, `recipients`, `sent_at`, `subject`, `attachments`, `sha256`
- Given the filename, Then `dsid` is the 32-hex id and `thread_date` is the slug's `YYYYMMDD`
- Given the thread, Then `thread_title` is line 1 and is the same on every record of that thread
- Given `message_index`, Then it is 0-based and in file order
- Given `recipients`, Then it is `to + cc` in that order
- Given a headerless thread, Then one record is returned with empty sender/recipients/subject, `sent_at` from `thread_date`, and a `headers_missing` flag
- Given the corpus, Then 578,254 records are produced from 121,390 threads

**Example with real data**
```python
MessageRecord(
    dsid="dsid_000025680c494c78b8005828c90c9293",
    thread_title="Payment orchestration: allocating regional seat charges across entities",
    thread_date="20260625",
    message_index=1,
    sender="Vivek Kulkarni <vivek.kulkarni@redwood.ai>",
    recipients=["Amal Khan <amal.khan@greenlinehealth.com>",
                "Kimberly Park <kimberly_park@redwood.ai>", …],
    sent_at="2026-06-25T18:05:00+00:00",
    subject="Re: Invoice & VAT approach for multi-entity pilot (Greenline)",
    attachments=["entity_mapping_template.xlsx"],
    sha256="…",
)
```
Note `thread_title` and `subject` say different things — true of 65% of threads, and the
reason both are embedded.

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus. `MessageRecord` is a frozen dataclass; flat values only, so it
serialises to a vector-store payload without transformation.

*Maintainability:* the ten fields are the contract for everything downstream; adding an
eleventh is a story of its own, because it changes the vector-store payload.
*Observability:* every record carries `headers_missing`, `date_assumed_utc` and
`body_empty`, so the awkward cases are queryable rather than invisible.

**Dependencies** APIs data contracts: GMAIL-3,4,5,6,7 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-8b  Message truth set: real messages with hand-checked output  ⬜

**Status:** To do. Built after GMAIL-8, so it can check the finished record and not only single functions.

**Background**
GMAIL-3, 4, 5 and 6 each pin real-corpus **counts** measured by a throwaway script. A count can
match while one message is wrong. That already happened once: the standard library counted
111,029 colon-offset dates as parsed, and only reading real values showed the zone was lost.
The other sources have a hand-checked set for this reason (PARSE-17 headings, SLACK-8b, LINEAR-3).
The escape story has a small one for its own question (`tests/fixtures/gmail_escape/expected.json`,
40 occurrences), but nothing covers the parsing stories.

**As a** pipeline developer
**I want to** real messages with the expected output written by hand
**So that** each rule is checked on individual messages, not only on totals

**Acceptance Criteria (Gherkin)**
- Given 30 to 40 real messages copied from `data/gmail/raw/` into `tests/fixtures/gmail_truth/`, When each is read by `message_records`, Then sender, recipients, `sent_at`, offset, `assumed_utc`, subject and quote-stripped body match the hand-written `expected.json`
- Given the fixture set, Then every edge case below is covered by at least one message, chosen from real data (not made up)
- Given a rule change that alters any expected value, Then the test fails and names the message and field
- Given the expected file, Then each entry records who checked it and on what date; an unchecked draft is marked as a draft

**Edge cases to cover (each found in the real corpus while building GMAIL-3 to 6)**
- Message shape: no `From:` line (189); date before `From:` (GMAIL-3b); preamble text
- Headers: wrapped `To:`/`Cc:` line; `Sent:` instead of `Date:`; no `Cc:`; `Bcc:` present; `Attachments:` line right after the subject; name with a comma (`Ruiz, Elena <a@b>`); `(none)` or `;` recipient list
- Dates: colon offset (`-07:00`); `-0000`; no zone (assumed UTC); named zone (`PDT`, `PT`); 12-hour clock with PM; full weekday and month names; a stray PM on a 24-hour time; one of the 126 unreadable dates
- Quotes: quote at the bottom; quote at the top with the answer below it (9,108 messages); author text on both sides (19,961); inline answers between `>` lines; nested `>>`; quote only (780); `On … wrote:` with no `>` after it (kept, flagged); a forward (kept); quoted attachment line
- Cleaning residue: a literal `\r` (GMAIL-1b)

**Who labels:** the expected values are drafted from the code's output and the raw text, then **checked by a person** before the story is marked done. A truth set the author both wrote and checked is only a regression test, not a truth set, so the file says which entries a person has checked.

**Non-functional Requirements**
Shared rules apply. Fixtures are real message text, so the set stays small; nothing here needs the full corpus and the tests always run.

**Dependencies** APIs data contracts: GMAIL-8 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-9  Messages corpus: jsonl and reconciliation  ⬜

**Status:** To do.

**Background**
Writes the records to disk so stage 3 never re-parses, and proves nothing was lost.

**As a** pipeline developer
**I want to** write the message records with a manifest that reconciles counts
**So that** a lost message fails a test instead of quietly lowering recall

**Acceptance Criteria (Gherkin)**
- Given `data/gmail/clean/`, Then `data/gmail/messages/` holds one `.jsonl` per input slice, one record per line
- Given `_manifest.json`, Then each row has `file`, `clean_sha256`, `messages`, `headers_missing`, `quoted_chars`
- Given the manifest, Then `sum(messages) == 578,254` and `sum(headers_missing) == 189`
- Given a second run, Then every file is byte-identical
- Given any thread, Then its `dsid` appears in at least one record

**Example with real data**
```json
{"file": "dsid_0070cd596374404085ed0cbca4e3a9e2__20280316-renewal-paperwork….txt",
 "clean_sha256": "…", "messages": 1, "headers_missing": 1, "quoted_chars": 0}
```

**Non-functional Requirements**
Shared rules apply. Golden: `tests/golden/gmail_messages_fingerprint.json`, one sha256
over every record's `sha256` in `(dsid, message_index)` order.

*Maintainability:* jsonl, one record per line, so a single thread can be inspected with
`grep` and no tooling.
*Observability:* this is the reconciliation point. The run prints threads in, messages out,
and the four flag counts, and fails if `sum(messages) != 578,254` or a `dsid` is missing.

**Dependencies** APIs data contracts: GMAIL-8 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-10  to_document: let the library inject the context  ⬜

**Status:** To do.

**Background**
A reply reading *"Option 1 works for us — send the sample invoice"* is meaningless as a
vector on its own. It needs its thread title, subject, sender and date. **We do not build
that string.** LlamaIndex injects `metadata` into the embed text already;
`text_template`, `metadata_template` and `excluded_embed_metadata_keys` control it. The
ids (`dsid`, `sha256`, `message_index`) go in metadata for the join but are excluded from
the embedding, where they would be noise.

**As a** pipeline developer
**I want to** turn one `MessageRecord` into a LlamaIndex `Document`
**So that** context injection, filtering and citation all come from one metadata dict

**Acceptance Criteria (Gherkin)**
- Given a record, Then a `Document` is returned with `text` = the quote-stripped body and the ten fields in `metadata`
- Given the document, Then `doc_id` is `f"{dsid}:{message_index}"`
- Given `get_content(MetadataMode.EMBED)`, Then it contains `thread_title`, `subject`, `sender`, `sent_at` and **not** `dsid`, `sha256`, `message_index`
- Given `get_content(MetadataMode.LLM)`, Then it also contains `attachments`
- Given metadata values, Then all are `str`, `int` or `float` — no nested structures, because vector stores reject them
- Given a record with `body_empty`, Then no document is produced and the skip is counted

**Example with real data**
```
Thread: Payment orchestration: allocating regional seat charges across entities
Subject: Re: Invoice & VAT approach for multi-entity pilot (Greenline)
From: Vivek Kulkarni <vivek.kulkarni@redwood.ai>
Date: 2026-06-25T18:05:00+00:00

Hi Amal — thanks for the clear note and the PO. We can support both approaches…
```
That block is what the embedder sees, produced by `text_template`, not by our code.

**Non-functional Requirements**
Shared rules apply. No hand-built header strings anywhere in this module. Pure apart from
the `Document` construction.

*Maintainability:* what the embedder sees is data — the templates and excluded-key lists —
not code, so the "title in the header or not" ablation is a config change, not a diff.
*Observability:* the run writes one sample `get_content(MetadataMode.EMBED)` per 10,000
documents to the run log, so what was actually embedded is inspectable after the fact.

**Dependencies** APIs data contracts: GMAIL-8, `llama_index.core.Document` ·
Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-11  chunk_id: the same id every run  ⬜

**Status:** To do.

**Background**
`SentenceSplitter` defaults to `uuid4()`, which makes every run produce new ids and
breaks both the golden test and any incremental upsert. The chunker design already solved
this for Confluence with an `id_func`; the same idea, keyed on the message.

**As a** pipeline developer
**I want to** a deterministic node id
**So that** re-running ingestion upserts rather than duplicates

**Acceptance Criteria (Gherkin)**
- Given `(dsid, message_index, part_index)`, Then the id is `sha256` of them joined by `:`
- Given the same inputs twice, Then the same id
- Given a message that splits into 2 parts, Then the ids differ
- Given the splitter, Then it is passed as `id_func` and no node carries a uuid

**Example with real data**
```
sha256("dsid_000025680c494c78b8005828c90c9293:1:0") → "a7f3…"   (stable across runs)
```

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus.

**Dependencies** APIs data contracts: GMAIL-10 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-12  build_pipeline: configure, do not write  ⬜

**Status:** To do.

**Background**
`IngestionPipeline` gives us four things we would otherwise build: splitting the 5.3%
long tail, `doc_id` + hash dedup via a docstore (which is NFR7, idempotent re-runs),
`IngestionCache` so an ablation re-run only re-embeds what changed, and `num_workers` for
578,254 messages. This story is configuration and a test that the configuration holds.

**As a** pipeline developer
**I want to** one function returning the configured `IngestionPipeline`
**So that** every experiment runs the same pipeline with one thing changed

**Acceptance Criteria (Gherkin)**
- Given `build_pipeline(embed_model, vector_store)`, Then transformations are `[SentenceSplitter(chunk_size=512, id_func=chunk_id), embed_model]`
- Given the pipeline, Then a `docstore` and an `IngestionCache` are attached
- Given a message under 512 tokens, Then exactly one node comes out, with the body unchanged
- Given a message over 512 tokens, Then ≥ 2 nodes, each ≤ 512 tokens, each carrying the same `dsid`
- Given the same documents run twice against the docstore, Then the second run produces zero new nodes
- Given a document whose text changed, Then it is re-processed and upserted
- Given the corpus, Then ≈ 609,000 nodes and every one has a non-empty `dsid`

**Example with real data**
```
578,254 documents in  →  609k nodes out
  547,366 pass through whole (94.7%)
   30,888 split into 2 (p99 body 2,781 chars; max 6,282)
```

**Non-functional Requirements**
Shared rules apply, except *deterministic offline*: this story calls an embedder. The
splitter half is tested offline with a stub embedder; the embedded run is a separate
script, not a unit test.

*Maintainability:* one function returns the configured pipeline, so every experiment runs
the same object with one argument changed. No experiment builds its own pipeline.
*Observability:* the instrumentation handler from GMAIL-17 is attached here. A run logs
nodes produced, documents skipped by the docstore, cache hits, embed tokens and failures,
and writes progress often enough that a crash at message 400,000 is diagnosable and the
re-run is a docstore skip rather than a full re-embed.

**Dependencies** APIs data contracts: GMAIL-10, GMAIL-11, `IngestionPipeline`,
`SentenceSplitter`, `SimpleDocumentStore`, `IngestionCache` · Service Bus: N/A ·
Database: vector store collection created here · UI: N/A

---

## GMAIL-13  ThreadRollup: chunks back to threads  ⬜

**Status:** To do.

**Background**
The one piece of retrieval that is genuinely ours. The index is message-grained; the
benchmark's `expected_doc_ids` are thread `dsid`s. Without a roll-up, ten retrieved
chunks can be ten messages of the *same* thread — recall@10 of one document. With it, a
thread scores as its best chunk and the ten slots hold ten threads.

Thread expansion then pulls the winning chunk's siblings, which is the payoff of the
message split: the evidence is one reply, the context is the conversation.

**As a** pipeline developer
**I want to** a `BaseNodePostprocessor` that collapses chunks to threads
**So that** retrieval is scored in the unit the benchmark uses

**Acceptance Criteria (Gherkin)**
- Given scored nodes, When the postprocessor runs, Then at most one node per `dsid` survives, the one with the highest score
- Given the survivors, Then they are ordered by score, highest first
- Given `expand=True`, Then each survivor carries its thread's other messages in metadata, in `message_index` order
- Given `top_k=10` after roll-up, Then 10 distinct `dsid`s are returned when 10 exist
- Given nodes with no `dsid`, Then it raises — a node without a thread id is a bug upstream

**Example with real data**
```
before  5 chunks: dsid_000025… msg 1 (0.81), dsid_000025… msg 4 (0.77),
                  dsid_0003343… msg 2 (0.74), dsid_000025… msg 0 (0.71), …
after   2 threads: dsid_000025… (0.81), dsid_0003343… (0.74)
```

**Non-functional Requirements**
Shared rules apply. Pure given nodes in, nodes out — no store access inside the
postprocessor except the sibling fetch, which is one docstore call per survivor.

*Maintainability:* roll-up and expansion are two behaviours behind one flag, each tested
alone, because the ablation in design §8 turns expansion off.
*Observability:* logs chunks in, threads out and the collapse ratio per query. A ratio near
1 means chunks were spread thin; near 5 means one thread dominated — both worth seeing
before reading a recall number.

**Dependencies** APIs data contracts: `BaseNodePostprocessor`, GMAIL-12's docstore ·
Service Bus: N/A · Database: reads the docstore · UI: N/A

---

## GMAIL-14  build_retriever: hybrid, fused, reranked  ⬜

**Status:** To do.

**Background**
14 of the 55 Gmail questions turn on an exact identifier — `INC-9821`, `SUP-1842`,
`ADR-007` — which dense retrieval handles poorly. `QueryFusionRetriever` fuses a vector
retriever and `BM25Retriever` with reciprocal rank fusion; a reranker from
`node_postprocessors` orders what survives. All library; this story wires it and proves
the wiring with the exact-code questions.

**As a** pipeline developer
**I want to** one function returning the configured retriever
**So that** the dense-only vs hybrid vs hybrid+rerank ablation is one argument

**Acceptance Criteria (Gherkin)**
- Given `build_retriever(index, mode)`, Then `mode="dense"`, `"hybrid"` and `"hybrid_rerank"` each return a working retriever
- Given `"hybrid"`, Then it is a `QueryFusionRetriever` over a vector retriever and a `BM25Retriever` with RRF
- Given `"hybrid_rerank"`, Then a reranker postprocessor runs before `ThreadRollup`
- Given any mode, Then `ThreadRollup` is the last postprocessor
- Given the question containing `INC-9821`, Then the hybrid retriever returns its expected `dsid` and the dense-only one is recorded for comparison
- Given a query, Then the number of candidates before fusion is a parameter, defaulted to 50

**Example with real data**
```
"INC-9821: was the degraded GPU node an OOM or intermittent driver/kernel launch stalls?"
  dense-only  → the exact code contributes almost nothing to the vector
  hybrid      → BM25 matches 'INC-9821' verbatim; RRF lifts it
```

**Non-functional Requirements**
Shared rules apply, except *offline*: this story queries an index. Configuration only —
no scoring logic of our own beyond GMAIL-13.

*Maintainability:* the three modes are one argument, so "dense vs hybrid vs reranked" is
never three code paths that drift apart.
*Observability:* each query logs per-retriever candidate ids and scores before fusion, so a
miss can be attributed to the vector side, the BM25 side or the fusion itself.

**Dependencies** APIs data contracts: `QueryFusionRetriever`, `BM25Retriever`,
`node_postprocessors`, GMAIL-13 · Service Bus: N/A · Database: reads the vector store · UI: N/A

---

## GMAIL-15  recall_at_k: the number that decides everything  ⬜

**Status:** To do.

**Background**
55 of the benchmark's 500 questions touch Gmail: 42 Gmail-only, 13 also needing
Confluence, Jira, Slack, GitHub, Fireflies or Drive. 42 expect one document; 8 expect 3
to 9. This is the gate for every ablation in design §8, and the per-question misses are
what make a regression actionable.

**As a** pipeline developer
**I want to** score a retriever against the Gmail questions
**So that** each design bet is settled by a number rather than an argument

**Acceptance Criteria (Gherkin)**
- Given `questions.jsonl`, Then the 55 rows whose `source_types` include `gmail` are selected
- Given a retriever, Then recall@1, @5 and @10 are reported over `expected_doc_ids`
- Given a question expecting 9 documents, Then recall is the fraction found, not all-or-nothing
- Given a run, Then per-question misses are written with the question id, the expected `dsid`s and the `dsid`s actually returned
- Given two runs of the same configuration, Then the same numbers
- Given the 13 multi-source questions, Then they are reported separately — Gmail alone cannot answer them

**Example with real data**
```
qst_0031  expected ['dsid_ae068ee4…']  got ['dsid_ae068ee4…', …]   hit@1
qst_0184  expected 9 dsids             got 4 of 9                  recall 0.44
```

**Non-functional Requirements**
Shared rules apply, except *offline*: queries an index. The question file is downloaded
once to `data/gmail/questions.jsonl` with its sha256 in the manifest, so the gate cannot
move under us.

*Maintainability:* the scorer takes a retriever and returns numbers; it knows nothing about
how the retriever was built, so a new mode needs no change here.
*Observability:* every run writes a report with the configuration, the three recall numbers
and every miss — question id, expected `dsid`s, returned `dsid`s, and the rank the expected
thread reached if it was retrieved at all. Two reports diff cleanly, which is what makes an
ablation an answer rather than an opinion.

**Dependencies** APIs data contracts: GMAIL-14, `questions.jsonl` (release v1.0.0) ·
Service Bus: N/A · Database: reads the vector store · UI: N/A

---

## GMAIL-16  audit_gmail: every rule that can misfire, as a number  ⬜

**Status:** To do.

**Background**
Nine of the stories above define a rule that is an assumption about how 121,390 threads
were written, and on a corpus that size every assumption is wrong somewhere. The
`Attached:` trap is the proof: had GMAIL-7 shipped matching all five spellings, roughly
2,900 sentences would have become metadata, and nothing would have failed — recall would
just have been quietly worse. A rule that can misfire needs a count, not a unit test.

This is the same pattern as PARSE-14 (`tools/audit.py`) for Confluence: one pure function
per assumption, a corpus scan, a table with three real examples, `--json` so two runs
diff. **PARSE-14 is not built yet.** Rather than block Gmail behind it, this story builds
the Gmail runner now and matches PARSE-14's `Finding` type and `--json` contract exactly,
so a later story merges the two runners into one with no change to either's audits. That
merge is the cost of shipping now, and it is recorded in PARSE-14's story.

**As a** pipeline developer
**I want to** `tools/audit_gmail.py` to print one row per rule: name, matching threads, share of corpus, three example files with line numbers
**So that** a rule change is judged by which rows it moves, and no rule in the design is unmeasured

**Acceptance Criteria (Gherkin)**
- Given the corpus, When I run `uv run python tools/audit_gmail.py`, Then I get a table with one row per audit, each a pure function `audit_<name>(text) -> list[Finding]` in `tools/audits/gmail/`
- Given the rows, Then they are at least:

  | Audit | What it counts | Expected today |
  |---|---|---:|
  | `escape_missed` | threads with literal `\n` that whole-file `is_escaped` would skip, split into code (1–4 occurrences) and partial damage (5+) | 166 / 13 |
  | `no_from_thread` | threads with no `From:` at a line start | 189 |
  | `from_in_quote` | `From:` inside a quoted block, which must not open a message | 0 new blocks |
  | `header_order` | header blocks not in the `From → To → [Cc] → Date → Subject` shape | ~0.4% |
  | `date_rule` | `Date:` values per parsing rule, plus failures | 0 failures |
  | `date_assumed_utc` | values with no zone, read as UTC | reported |
  | `quote_opener_unmatched` | an `On … wrote:` line with no `>` line after it (kept, flagged by `strip_quotes`; 1,505 bodies) | small |
  | `body_empty` | messages that were only a quote | small |
  | `attachment_prose` | attachment-shaped lines holding no filename | ~2,900 `Attached:` |
  | `duplicate_chunk_id` | ids colliding across the corpus | 0 |
- Given a row, Then the count matches the number quoted in the [Gmail design](../design/3-gmail-system-design.md) for that rule, or the design is updated in the same PR
- Given `--json`, Then the same table as JSON, using PARSE-14's `Finding` shape
- Given `pipeline/`, When I grep for `audit`, Then there are no matches — tools only
- Given the full corpus, Then the run finishes in under 120 s

**Example with real data**
```
attachment_prose        2,904 lines   2.4% of threads
  dsid_000025680c49…  line 61  'Attached: sample invoice mock (internal) and entity mapping…'
  dsid_00ada6ccfbef…  line 44  'Attached: the latest order form and a redlined term sheet…'
  dsid_0081189fd7fa…  line 12  'Attached: MAP snapshot and evidence plan for review.'
→ all three are prose. GMAIL-7 excludes `Attached:`; this row is the evidence, and it
  becomes the regression test if anyone proposes including it.
```

**Non-functional Requirements**
Shared rules apply. Each audit is one pure function over one thread's text, about 15 lines,
with doctests; the runner only loops and prints.

*Maintainability:* every new rule added to the design gets an audit row in the same PR —
that is the rule this story exists to enforce. The `Finding` type is imported from the
shape PARSE-14 defines, not redefined, so the later merge is a deletion.
*Observability:* this story **is** the build-time observability. `--json` output is
committed per run under `data/gmail/audits/`, so a rule change shows as a diff.

**Dependencies** APIs data contracts: GMAIL-1…9, PARSE-14's `Finding` shape (contract only;
the runner is not needed) · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-17  Run log: instrumentation for the embed and query runs  ⬜

**Status:** To do.

**Background**
Stories 1–9 are offline and provable by fingerprints. Everything from GMAIL-12 on calls an
embedder or a store, where fingerprints cannot reach: a run over 578,254 messages that
dies at 400,000 leaves no evidence of where or why, and the 190 M token estimate stays an
estimate. There is no logging anywhere in `pipeline/` today and no logging dependency, so
this is new ground — which is why it uses the library rather than inventing a convention.

`llama_index.core.instrumentation` is already in `llama-index-core==0.14.24`: a
`Dispatcher` emits events, `BaseEventHandler` receives them, `SpanHandler` brackets the
call. Attaching one handler that appends JSONL is the whole story. No external service, no
new dependency, no tracing backend.

**As a** pipeline developer
**I want to** one event handler that writes every embed and query event to a run log
**So that** a failed run is diagnosable and a cost estimate becomes a measurement

**Acceptance Criteria (Gherkin)**
- Given `RunLog(path)`, When it is attached to the dispatcher, Then every LlamaIndex event reaches it and is appended as one JSON object per line
- Given an embedding run, Then the log records batches completed, nodes embedded, tokens, elapsed time and every exception with the `dsid` being processed at the time
- Given a run that crashes, Then the log is readable and names the last `dsid` — a re-run relies on the docstore to skip what is already done
- Given a query run, Then the log records the query, per-retriever candidates before fusion, scores after fusion and after rerank, and the `dsid`s after roll-up
- Given a completed embed run, Then a summary reports total tokens against the 190 M estimate and total nodes against the 609 k estimate
- Given the handler, Then it never raises into the pipeline — a logging failure degrades to a counter, it does not fail an eight-hour run
- Given `pipeline/`, Then no module contains a bare `print`

**Example with real data**
```json
{"ts":"2026-09-23T10:14:02Z","event":"EmbeddingEndEvent","batch":412,
 "nodes":10240,"tokens":3180422,"elapsed_s":91.4}
{"ts":"2026-09-23T10:14:07Z","event":"error","dsid":"dsid_0070cd5963744040…",
 "exc":"RateLimitError","batch":413}
{"ts":"2026-09-23T11:02:55Z","event":"run_summary","nodes":609118,
 "tokens":188942301,"estimate_tokens":190000000,"failed":0}
```

**Non-functional Requirements**
Shared rules apply, except *deterministic offline*: the handler observes runs that call a
model. The handler itself is tested offline by dispatching synthetic events.

*Maintainability:* one handler class, attached in one place (GMAIL-12's `build_pipeline`).
No module logs for itself, so there is one format and one destination to change.
*Observability:* this story is the runtime half of the shared observability rule. The log
is JSONL under `data/gmail/runs/<timestamp>.jsonl` — greppable, diffable, no viewer needed.

**Dependencies** APIs data contracts: `llama_index.core.instrumentation` (`Dispatcher`,
`BaseEventHandler`, `SpanHandler`), GMAIL-12, GMAIL-14 · Service Bus: N/A ·
Database: N/A · UI: N/A

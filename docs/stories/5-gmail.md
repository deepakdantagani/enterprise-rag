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
    messages.py    GMAIL-3,4,6,7  split_messages, parse_headers, strip_quotes, attachments
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
| 5 | GMAIL-5 normalise_date | every `Date:` to one UTC instant; stdlib covers 98.21%, a third rule covers the rest |
| 6 | GMAIL-6 strip_quotes | drop the `On … wrote:` block and its `>` lines |
| 7 | GMAIL-7 attachments | filenames from `Attachment(s):`; **never** from prose `Attached:` |
| 8 | GMAIL-8 message_records | assemble the ten fields per message, thread fields from the filename and line 1 |
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

## GMAIL-4  parse_headers: the five fields of one block  ⬜

**Status:** To do.

**Background**
Header order is `From → To → [Cc] → Date → Subject` in 99.6% of blocks. `Cc` is absent in
19%. `Bcc` (79 occurrences), `Reply-To` (2) and `References` (56) appear and are ignored.
Addresses are comma-separated and mix `Name <addr>` with bare `addr@host`.

**As a** pipeline developer
**I want to** read the header block of one message into a typed record
**So that** sender, recipients, date and subject are metadata rather than text

**Acceptance Criteria (Gherkin)**
- Given a block, When `parse_headers` runs, Then it returns `from_`, `to`, `cc`, `date_raw`, `subject` and the body with header lines removed
- Given `To: A <a@x>, B <b@y>`, Then `to == ["A <a@x>", "B <b@y>"]`, split on commas outside angle brackets
- Given a block with no `Cc:`, Then `cc == []`
- Given a header key we ignore (`Bcc`, `Reply-To`, `References`), Then it is removed from the body and not returned
- Given a block whose headers are out of order, Then all five are still found
- Given a block with no headers (GMAIL-3's 189), Then all fields are empty and the body is the whole block

**Example with real data**
```
From: Vivek Kulkarni <vivek.kulkarni@redwood.ai>
To: Amal Khan <amal.khan@greenlinehealth.com>
Cc: Kimberly Park <kimberly_park@redwood.ai>, Marissa Cole <marissa_cole@redwood.ai>
Date: Thu, 25 Jun 2026 11:05:00 -07:00
Subject: Re: Invoice & VAT approach for multi-entity pilot (Greenline)
→ from_='Vivek Kulkarni <vivek.kulkarni@redwood.ai>'
  to=['Amal Khan <amal.khan@greenlinehealth.com>']
  cc=['Kimberly Park <kimberly_park@redwood.ai>', 'Marissa Cole <marissa_cole@redwood.ai>']
  date_raw='Thu, 25 Jun 2026 11:05:00 -07:00'
  subject='Re: Invoice & VAT approach for multi-entity pilot (Greenline)'
```

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus. Never parses the date here — that is GMAIL-5.

*Maintainability:* header keys we ignore are listed in one constant, so adding `Bcc`
handling later is a one-line change with a test, not a hunt.
*Observability:* audit row `header_order` counts blocks whose order is not the 99.6% shape,
and `header_missing_field` counts blocks short a field — both with three real examples.

**Dependencies** APIs data contracts: GMAIL-3 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-5  normalise_date: 575,915 headers, one instant each  ⬜

**Status:** To do.

**Background**
Measured over every `Date:` header in the corpus. The Python standard library parses
**565,582 of 575,915 (98.21%)** with two calls: `datetime.fromisoformat` for the ISO
family and `email.utils.parsedate_to_datetime` for RFC-2822. The remaining **10,333
headers in 2,012 distinct shapes** need a third rule, and the SLO budget for unparsed
dates is zero, so the rule is required, not optional.

The stragglers are three families:

| Family | Count (top shapes) | Example |
|---|---:|---|
| ISO date with a space instead of `T`, seconds optional | 2,119 + 1,236 | `2026-09-17 09:12 -0400` · `2026-04-15 09:12:05 -0700` |
| Named US/EU zone instead of an offset | 959 + 481 + 39 + 19 | `2026-10-20 09:12 PDT` · `2026-02-12 15:07 PST` · `2026-11-15 13:12 UTC` · `2026-11-24 08:12 CET` |
| Gmail's display format, 12-hour clock | 91 + 54 + 25 + 22 | `2027-04-18 09:12 AM -0700` · `Tue, Feb 10, 2026 at 10:04 AM PST` · `Tue, Feb 24, 2026 at 3:10 PM` |

Note `-07:00` with a colon appears in RFC-2822-shaped values, and `Tue, Feb 24, 2026 at
3:10 PM` carries no zone at all.

**As a** pipeline developer
**I want to** turn any `Date:` value into one UTC instant
**So that** two date families and 2,012 stray shapes do not become two kinds of metadata

**Acceptance Criteria (Gherkin)**
- Given `2026-06-25T09:12:00-07:00`, Then the result is `2026-06-25T16:12:00+00:00`
- Given `Thu, 25 Jun 2026 09:12:00 -0700`, Then the result is the same instant
- Given `Thu, 25 Jun 2026 11:05:00 -07:00` (colon in the offset), Then it parses
- Given `2026-09-17 09:12 -0400`, Then it parses (space form, no seconds)
- Given `2026-10-20 09:12 PDT`, Then the named zone resolves to `-0700`
- Given `Tue, Feb 24, 2026 at 3:10 PM` with no zone, Then it is read as UTC and the record is flagged `date_assumed_utc`
- Given an unparseable value, Then the function raises; it never returns a default
- Given the corpus, Then all 575,915 headers parse and the count of `date_assumed_utc` is reported

**Example with real data**
```
'Thu, 25 Jun 2026 09:12:00 -0700'      → '2026-06-25T16:12:00+00:00'   (parsedate_to_datetime)
'2026-09-05T15:08:00Z'                 → '2026-09-05T15:08:00+00:00'   (fromisoformat)
'2026-10-20 09:12 PDT'                 → '2026-10-20T16:12:00+00:00'   (third rule)
'Tue, Feb 10, 2026 at 10:04 AM PST'    → '2026-02-10T18:04:00+00:00'   (third rule)
```

**Non-functional Requirements**
Shared rules apply. Pure, offline, no `dateutil` dependency unless the third rule proves
longer than the library call it would replace — decide in the PR with both written.

*Maintainability:* the three rules are three functions tried in order, each with its own
doctests, so a new shape is a new rule and its own test — never a longer regex.
*Observability:* the record carries which rule parsed it and `date_assumed_utc`. Audit row
`date_rule` reports the split across the three rules and must show zero failures; if the
third rule's share moves after a change, the number says so.

**Dependencies** APIs data contracts: GMAIL-4 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-6  strip_quotes: remove what is already indexed  ⬜

**Status:** To do.

**Background**
61,922 threads (51%) quote an earlier message back. That text is 42.8 M chars, 6.3% of
all body text, and every word of it is already embedded on the message it came from.
Leaving it in means a question matches both the original and every reply that quoted it.

Two quote openers appear:
`On Mon, May 10, 2027 at 08:23 Naomi Feldman <naomi@…> wrote:` and
`On 2026-09-05 10:12, Claire Dawson wrote:`. Both are followed by `>`-prefixed lines.

**As a** pipeline developer
**I want to** cut a message body at its quote marker
**So that** each message embeds only what its author wrote

**Acceptance Criteria (Gherkin)**
- Given a body with `On … wrote:`, Then the text from that line to the end is removed
- Given both opener shapes, Then both are matched
- Given a body whose lines start with `>` but has no opener, Then the `>` lines are removed
- Given a body with no quoting, Then it is returned unchanged
- Given a body that is *only* a quote, Then the result is empty and the record is flagged `body_empty`
- Given the corpus, Then 42.8 M chars are removed and the removed count is reported per thread

**Example with real data**

`dsid_0003343918ed4f56960a7d38b9848893__20260908-ed…`:

```
before  'Subject: Re: Edge node licensing — clarify platform fee credits'
        ''
        'On 2026-09-05 10:12, Claire Dawson wrote:'
        '> Thanks for the walkthrough earlier. We captured our prioritized constraints in'
        '> the attached Novus-VPC-Requirements.pdf but wanted a couple of clarifications…'

after   (the message's own text only; the quote is already a record of its own)
```

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus. The quote stays in the clean file — only the record's
`body` loses it, so nothing is destroyed on disk.

*Maintainability:* the two opener shapes are two patterns in one constant with a real
example beside each, so a third shape is an entry, not a rewrite.
*Observability:* `quoted_chars_removed` per thread in the manifest, summing to 42.8 M.
Audit rows: `quote_opener_unmatched` (a `>` block with no opener) and `body_empty`
(a message that was only a quote) — both must stay small and are listed with examples.

**Dependencies** APIs data contracts: GMAIL-3 · Service Bus: N/A · Database: N/A · UI: N/A

---

## GMAIL-7  attachments: filenames, not prose  ⬜

**Status:** To do.

**Background**
110,768 threads mention attachments, under five spellings: `Attachment:`,
`Attachments:`, `attachment:`, `attachments:` and `Attached:`. **`Attached:` is a trap.**
It is usually a sentence, not a list:

> `Attached: sample invoice mock (internal) and entity mapping template. No need to do a
> formal review — a short checklist will do.`

Matching it would put a sentence into a metadata field. The rule takes the four
`Attachment(s):` spellings, and accepts a value only when it looks like filenames.

**As a** pipeline developer
**I want to** pull attachment filenames out of a message block
**So that** attachments are filterable metadata instead of body text

**Acceptance Criteria (Gherkin)**
- Given `Attachment: Greenline_PO_3042.pdf (application/pdf)`, Then `["Greenline_PO_3042.pdf"]`
- Given `Attachments: entity_mapping_template.xlsx, Greenline_SOW_v2.docx`, Then both filenames, in order
- Given lowercase `attachments:`, Then it matches
- Given `Attached: sample invoice mock (internal) and entity mapping template. No need…`, Then `[]` — the line is prose and stays in the body
- Given a value with no `.<ext>` token, Then `[]`
- Given a message with no attachment line, Then `[]`

**Example with real data**
```
'Attachment: Greenline_PO_3042.pdf (application/pdf)'          → ['Greenline_PO_3042.pdf']
'Attachments: entity_mapping_template.xlsx, Greenline_SOW_v2.docx'
                                                               → ['entity_mapping_template.xlsx',
                                                                  'Greenline_SOW_v2.docx']
'attachments: ClearWave_MSA_redline_v1.docx'                   → ['ClearWave_MSA_redline_v1.docx']
'Attached: sample invoice mock (internal) and entity mapping…' → []
```

**Non-functional Requirements**
Shared rules apply. Pure.

*Maintainability:* one function, no state; the id scheme is documented beside it because
changing it invalidates every stored vector.
*Observability:* audit row `duplicate_chunk_id` must be 0 over the corpus. The MIME string in parentheses is discarded; no attachment
bytes exist in the corpus, so a type adds nothing.

*Maintainability:* the accepted spellings and the filename test are two constants at the
top of the module, next to the `Attached:` prose example that explains the exclusion.
*Observability:* audit row `attachment_prose` counts lines that look like an attachment
header but hold no filename — the rule that would silently put a sentence into metadata.
Expect ~2,900 excluded `Attached:` lines and near zero false accepts.

**Dependencies** APIs data contracts: GMAIL-3 · Service Bus: N/A · Database: N/A · UI: N/A

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

## GMAIL-9  Messages corpus: jsonl and reconciliation  ⬜

**Status:** To do.

**Background**
Writes the records to disk so stage 3 never re-parses, and proves nothing was lost.

**As a** pipeline developer
**I want to** write the message records with a manifest that reconciles counts
**So that** a lost message fails a test instead of quietly lowering recall

**Acceptance Criteria (Gherkin)**
- Given `data/gmail/clean/`, Then `data/gmail/messages/` holds one `.jsonl` per input slice, one record per line
- Given `_manifest.json`, Then each row has `file`, `clean_sha256`, `messages`, `headers_missing`, `quoted_chars_removed`
- Given the manifest, Then `sum(messages) == 578,254` and `sum(headers_missing) == 189`
- Given a second run, Then every file is byte-identical
- Given any thread, Then its `dsid` appears in at least one record

**Example with real data**
```json
{"file": "dsid_0070cd596374404085ed0cbca4e3a9e2__20280316-renewal-paperwork….txt",
 "clean_sha256": "…", "messages": 1, "headers_missing": 1, "quoted_chars_removed": 0}
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
  | `quote_opener_unmatched` | a `>` block with no `On … wrote:` opener | small |
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

# Stories: rules, template, glossary and index

How every story is written, whatever file it lives in. One story = one function = one PR
(about 60 lines including its tests). A story that is still module-level gets split into
one-function sub-stories (a, b, c) when we reach it, not before. Every sub-story carries an "Example with real data"
section: a before/after taken from the actual corpus, so the change is concrete. Each story is independent:
it can be built and merged without the others, because the existing modules keep
working until a later story switches the caller over. TDD on every story: write the
acceptance tests first (red), then the code (green), then the PR.

Heading icons: ✅ Done · ⬜ To do (mirror the Status line).

Template for every story, in this order: Status · As a · I want to · So that ·
Acceptance Criteria (Gherkin) · Example with real data · Non-functional Requirements ·
Dependencies (APIs data contracts · Service Bus · Database updates · UI).

Shared non-functional requirements (apply to every story):
- Deterministic: same input, same output, no network, no model calls.
- Behaviour-preserving: after the story, `uv run python -m unittest discover tests` is
  green and the clean-folder manifest sha256 values are unchanged.
- Readable: top-of-file story, one idea per function, input -> output doctests, early returns.
- Maintainable: reuse before writing. Before adding a function, name the existing module or
  library call it replaces, or say in the PR why neither fits. One idea per function, one
  function per PR, about 60 lines including tests. Every module opens with the story it
  implements and the real corpus example that made it necessary, so the next person reads
  the why before the how.
- Observable: every stage leaves evidence. A manifest row per file carrying the counts that
  stage owns, and a count that reconciles with the stage before it. A rule that can misfire
  gets an audit row in the same PR — a pure function, a corpus count, three real examples —
  so a wrong rule shows up as a number instead of as lost recall. Anything that calls a
  model or a store emits events to a run log, never a bare `print`.
- No Service Bus, database, or UI in any story below (marked N/A).

Glossary (terms used across the stories; a story should make sense without chat history):
- **Raw file**: one Confluence page exported as `.txt`, exactly as received, under `data/confluence/raw/`. 5,189 files.
- **Clean file**: the same page after the cleaning rules, under `data/confluence/clean/`, same file name.
- **JSON-escaped**: the export wrote the page body as a JSON string, so a line break is the two characters `\n`
  and a quote is `\"`. 910 of the raw files are like this. "Unescape" turns them back into real characters.
- **sha256**: a 64-character hex fingerprint of some bytes. Same bytes, same fingerprint; one byte changed, a completely different one. Used to prove which raw bytes produced which clean bytes.
- **Manifest**: `data/confluence/clean/_manifest.json`, one row per file (see PARSE-2b for the row). It is the audit trail of the cleaning step and the input to the triage gate (PARSE-10).
- **Golden fingerprint**: `tests/golden/corpus_fingerprint.json`, one sha256 over every clean file's sha256 in manifest order. If a refactor changes any clean file by one byte, this test fails. It is how we know a story preserved behaviour.
- **Bucket**: which markup style a clean file uses (A `#` headings, B underlined headings, C plain labels, D prose). See PARSE-3.
- **Label rule**: our own rule that finds headings written as bare lines such as `Overview` with no `#`. See PARSE-4.
- **markdown-it**: the Markdown parser library (`markdown-it-py`) we use for headings, lists, tables and code fences.
- **LlamaIndex**: the RAG framework the pipeline must plug into; our chunks become its `TextNode`s. See PARSE-9.

## Index

Stories live in `docs/stories/`, one file per stage, numbered in pipeline order: `1-parsing`,
`2-chunking`, `3-llamaindex`, `4-tools`. Each additional source then gets its own slot,
assigned alphabetically so branches built in parallel do not collide: `5-gmail`, `6-linear`,
`7-slack`; `docs/design/` follows the same scheme, `3-gmail`, `4-linear`, `5-slack`. Story
numbers are stable and prefixed by source — `PARSE-n` for the Confluence stages, `GMAIL-n`,
`LINEAR-n`, `SLACK-n` — and a story keeps its number when it moves. The glossary above is
Confluence's; each source file carries its own, so a story can be read without the others.

| Story | File |
|---|---|
| PARSE-1  Text cleaning rules as a pure module  ✅ | [1-parsing.md](stories/1-parsing.md) |
| PARSE-2  Corpus writer  (split into one function per PR) | [1-parsing.md](stories/1-parsing.md) |
| PARSE-3  Bucket classifier  ✅ | [1-parsing.md](stories/1-parsing.md) |
| PARSE-4  Label rule as its own module  (split into one function per PR) | [1-parsing.md](stories/1-parsing.md) |
| PARSE-5  Heading detector interface + Markdown implementation  (split into one function per PR) | [1-parsing.md](stories/1-parsing.md) |
| PARSE-6  Label heading detector + selector  (split into one function per PR) | [1-parsing.md](stories/1-parsing.md) |
| PARSE-7  Blocks from markdown-it  (split into one function per PR) | [1-parsing.md](stories/1-parsing.md) |
| PARSE-17  Heading truth set: real files with hand-checked headings  ✅ | [2-chunking.md](stories/2-chunking.md) |
| PARSE-8  Every clean file becomes Markdown, one pass per file  (8a, 8b1, 8b2, 8c, 8d) | [2-chunking.md](stories/2-chunking.md) |
| PARSE-9  LlamaIndex adapter: the chunker is library code  (9a, 9b, 9c) | [3-llamaindex.md](stories/3-llamaindex.md) |
| PARSE-10  Triage gate on the new modules  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-11  Debug and measurement tools out of the pipeline  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-13  Document type from the title  ⬜ | [1-parsing.md](stories/1-parsing.md) |
| PARSE-14  Assumption audit: every chunking assumption as a corpus count  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-16  Chunking validation: recall@20 on the benchmark questions  ⬜ | [3-llamaindex.md](stories/3-llamaindex.md) |
| GMAIL-1 … GMAIL-9  Raw threads to message records  ⬜ | [5-gmail.md](stories/5-gmail.md) |
| GMAIL-10 … GMAIL-12  Message records to LlamaIndex nodes  ⬜ | [5-gmail.md](stories/5-gmail.md) |
| GMAIL-13 … GMAIL-15  Thread roll-up, hybrid retrieval, recall@k  ⬜ | [5-gmail.md](stories/5-gmail.md) |
| GMAIL-16  Gmail audit tool: every rule as a corpus count  ⬜ | [5-gmail.md](stories/5-gmail.md) |
| GMAIL-17  Run log: LlamaIndex instrumentation for the embed and query runs  ⬜ | [5-gmail.md](stories/5-gmail.md) |
| SLACK-0  Corpus profile  ✅ | [7-slack.md](stories/7-slack.md) |
| SLACK-1  `unescape`  ✅ | [7-slack.md](stories/7-slack.md) |
| SLACK-2  `normalize_whitespace`  ✅ | [7-slack.md](stories/7-slack.md) |
| SLACK-3  Events and a handler (instrumentation)  ✅ | [7-slack.md](stories/7-slack.md) |
| SLACK-4  `write_clean_corpus` + manifest  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-5  `channel_of`  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-6  `split_messages`  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-7  `parse_speaker`  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-8  `parse_thread` + truth set  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-9  `chunk_thread`  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-10  `to_text_node`  ⬜ | [7-slack.md](stories/7-slack.md) |
| SLACK-11  Embed + BM25 hybrid index  (module-level) | [7-slack.md](stories/7-slack.md) |
| SLACK-12  recall@20 on the benchmark questions  (module-level) | [7-slack.md](stories/7-slack.md) |
| LINEAR-1  Shared cleaning  (1a split by source, 1b escape audit, 1c `normalize_text`) ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-2  `parse_filename`: the id comes from the name  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-3  Activity truth set: real files with hand-labelled lines  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-4  `activity_entry`: judge every line on its own  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-5  `narrative_sections`: group the prose  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-6  `to_nodes`: pack the ticket  (6a, 6b) ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-7  Reuse the corpus writer for a second source  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-8  Golden fingerprints for the Linear corpus  ⬜ | [6-linear.md](stories/6-linear.md) |
| LINEAR-9  Counts for every stage (`_stats.json`)  ⬜ | [6-linear.md](stories/6-linear.md) |

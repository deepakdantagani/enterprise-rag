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

Stories live in `docs/stories/`, one file per stage, numbered in pipeline order: `1-parsing`, `2-chunking`, `3-llamaindex`, `4-tools`. Story numbers (PARSE-n) are stable; a story keeps its number when it moves.

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
| PARSE-8  Every clean file becomes Markdown, one pass per file  (8a–8d) | [2-chunking.md](stories/2-chunking.md) |
| PARSE-9  LlamaIndex adapter: the chunker is library code  (9a, 9b, 9c) | [3-llamaindex.md](stories/3-llamaindex.md) |
| PARSE-10  Triage gate on the new modules  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-11  Debug and measurement tools out of the pipeline  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-13  Document type from the title  ⬜ | [1-parsing.md](stories/1-parsing.md) |
| PARSE-14  Assumption audit: every chunking assumption as a corpus count  ⬜ | [4-tools.md](stories/4-tools.md) |
| PARSE-16  Chunking validation: recall@20 on the benchmark questions  ⬜ | [3-llamaindex.md](stories/3-llamaindex.md) |

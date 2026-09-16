# enterprise-rag

Enterprise knowledge-base RAG on [EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench), built on LlamaIndex. See [PROJECT_GOAL.md](PROJECT_GOAL.md) and [AGENTS.md](AGENTS.md).

## Layout

```
pipeline/                 active ingestion code (a Python package), pure functions, one idea per module
  cleaning.py             raw export -> clean text (unescape JSON-escaped bodies, fix wiki markup, tidy whitespace)
  corpus.py, manifest.py  write data/confluence/clean/ and one manifest row (raw/clean sha256) per file
  label_rule.py           our rule for bare-label headings such as `Overview:` (no library finds these)
  markdown.py             the one shared markdown-it instance
  to_markdown.py          planned (PARSE-8): one pass per file, # on every heading (any style), same line count
  buckets.py, headings.py, blocks.py   the previous heading detectors; retired by PARSE-8d once to_markdown matches the goldens
  nodes.py                planned (PARSE-9): LlamaIndex MarkdownNodeParser + SentenceSplitter, stable ids, line ranges
tests/                    unit tests, 13 fixture documents, golden corpus fingerprints
tools/                    planned: audit and measurement scripts (PARSE-11, PARSE-14), outside pipeline/
docs/stories.md           story rules + index; stories in docs/stories/<n>-<stage>.md
docs/design/              system designs: 1-parser, 2-chunker
docs/decisions/           one short record per decision (why, evidence, rejected options)
docs/research/            background notes (corpus review, parsing research)
docs/archive/             superseded plans, kept for the record
archive/v0/               the first, monolithic version; its corpus fingerprints seeded the goldens
data/confluence/          gitignored: archives/ raw/ clean/ markdown/ validation/ (+ manifest)
```

## Run

```sh
uv sync                                   # installs pinned deps into .venv
uv run python -m unittest discover tests  # unit tests + corpus goldens (corpus tests skip if data/ is missing)
```

The corpus writer (PARSE-2) fills `data/confluence/clean/` and `_manifest.json` (raw/clean sha256 per file). The triage gate and the command-line entry points are stories PARSE-10 and PARSE-11; until then the v0 versions live under `archive/v0/`.

## Pipeline in one paragraph

Raw Confluence exports are cleaned (`cleaning`). Then one pass per page (`to_markdown`, planned) finds every heading whatever its style (markdown-it for `#` and underlined headings, our label rule for bare lines like `Overview:`, which no library detects) and writes it as `#` into a Markdown copy with the same line count, so LlamaIndex's own `MarkdownNodeParser` can cut every page into one node per section and `SentenceSplitter` can trim the few sections over 512 tokens (`nodes`, planned). Every node carries the title, the section breadcrumb, an id derived from the file hash and line range, and that exact line range for citation. No custom chunker. Why: [docs/design/2-chunker-system-design.md](docs/design/2-chunker-system-design.md); why this parser and not a hosted one: [docs/decisions/0001-confluence-parser.md](docs/decisions/0001-confluence-parser.md).

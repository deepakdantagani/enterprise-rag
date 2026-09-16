# enterprise-rag

Enterprise knowledge-base RAG on [EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench), built on LlamaIndex. See [PROJECT_GOAL.md](PROJECT_GOAL.md) and [AGENTS.md](AGENTS.md).

## Layout

```
pipeline/                 active ingestion code (a Python package), pure functions, one idea per module
  cleaning.py             raw export -> clean text (unescape JSON-escaped bodies, fix wiki markup, tidy whitespace)
  corpus.py, manifest.py  write data/confluence/clean/ and one manifest row (raw/clean sha256) per file
  buckets.py              which heading style a file uses: # / underlined / bare labels / prose
  label_rule.py           our rule for bare-label headings such as `Overview:` (no library finds these)
  headings.py             one detector per style -> list[Heading(line, level, text)]
  blocks.py, markdown.py  markdown-it block map: which lines are a list, table, code fence
  markdown_view.py        planned (PARSE-8): write # on every detected heading, same line count
  nodes.py                planned (PARSE-9): LlamaIndex MarkdownNodeParser + SentenceSplitter, stable ids, line ranges
tests/                    unit tests, 13 fixture documents, golden corpus fingerprints
tools/                    planned: audit and measurement scripts (PARSE-11, PARSE-14), outside pipeline/
docs/stories.md           story rules + index; stories in docs/stories/<n>-<stage>.md
docs/design/              system designs: 1-parser, 2-chunker
docs/decisions/           one short record per decision (why, evidence, rejected options)
docs/research/            longer background notes and plans
archive/v0/               the first, monolithic version; kept for its tests and fingerprints
data/confluence/          gitignored: archives/ raw/ clean/ markdown/ validation/ (+ manifest)
```

## Run

```sh
uv sync                                   # installs pinned deps into .venv
uv run python -m unittest discover tests  # unit tests + corpus goldens (corpus tests skip if data/ is missing)
```

The corpus writer (PARSE-2) fills `data/confluence/clean/` and `_manifest.json` (raw/clean sha256 per file). The triage gate and the command-line entry points are stories PARSE-10 and PARSE-11; until then the v0 versions live under `archive/v0/`.

## Pipeline in one paragraph

Raw Confluence exports are cleaned (`cleaning`), and their headings found whatever the style (`headings`: markdown-it for `#` and underlined headings, our label rule for bare lines like `Overview:`, which no library detects). Those headings are then written as `#` into a Markdown copy of each page with the same line count (`markdown_view`, planned), so LlamaIndex's own `MarkdownNodeParser` can cut every page into one node per section and `SentenceSplitter` can trim the few sections over 512 tokens (`nodes`, planned). Every node carries the title, the section breadcrumb, an id derived from the file hash and line range, and that exact line range for citation. No custom chunker. Why: [docs/design/2-chunker-system-design.md](docs/design/2-chunker-system-design.md); why this parser and not a hosted one: [docs/decisions/0001-confluence-parser.md](docs/decisions/0001-confluence-parser.md).

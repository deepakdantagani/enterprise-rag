# enterprise-rag

Enterprise knowledge-base RAG on [EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench), built on LlamaIndex. See [PROJECT_GOAL.md](PROJECT_GOAL.md) and [AGENTS.md](AGENTS.md).

## Layout

```
pipeline/                 active ingestion code (a Python package)
  preprocess.py           raw export -> clean text (unescape, whitespace, structure fixes)
  structure.py            bucket a file by markup style; plain-label heading rule
  triage.py               gate for new data: runs preprocess, buckets, flags files for review
  nodes.py                LlamaIndex integration: Documents -> section-aware TextNodes
tests/                    unit tests + 13 fixture documents (the validation sample set)
docs/decisions/           one short record per decision (why, evidence, rejected options)
docs/research/            longer background notes and plans
data/confluence/          gitignored: archives/ raw/ clean/ validation/ (+ manifests)
```

## Run

```sh
uv sync                                   # installs pinned deps into .venv
uv run python -m pipeline.triage          # raw -> clean, buckets, review list (exit 1 if any flagged)
uv run python -m pipeline.nodes           # print chunks for tests/fixtures/typical.md
uv run python -m unittest discover tests
```

Outputs of `triage` land in `data/confluence/clean/`: the cleaned files, `_manifest.json` (raw/clean sha256 per file), `_triage.json` and `_review.md` (files that need a human look, grouped by reason).

## Pipeline in one paragraph

Raw Confluence exports are normalized (`preprocess`), bucketed by how they express structure (`structure`), and gated (`triage`). Parsing is markdown-it-py with source line maps, plus a rule that promotes bare label lines like `Overview` to headings in files that have no markup. `nodes.ConfluenceNodeParser` turns each document into section-aligned chunks that never split a list, table, or code fence, and carries the title, section breadcrumb, and exact source line range on every node. Why this and not a hosted parser: [docs/decisions/0001-confluence-parser.md](docs/decisions/0001-confluence-parser.md).

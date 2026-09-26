# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Enterprise knowledge-base RAG on EnterpriseRAG-Bench, built on LlamaIndex (goal: top-10 on the leaderboard, see `PROJECT_GOAL.md`). Working rules are in `AGENTS.md`: follow them. The layout and a one-paragraph summary of the pipeline are in `README.md`.

## Commands

```sh
uv sync                                                  # install pinned deps into .venv
uv run python -m unittest discover tests                 # full suite: unit tests + corpus goldens (~7 min when data/ is present)
uv run python -m unittest tests.test_slack_thread        # one module
uv run python -m unittest tests.test_slack_thread.Record.test_participants_are_distinct_names_in_the_order_they_first_speak
uv run python -m pipeline.slack.corpus                   # 58 zips in data/slack/archives -> data/slack/clean + _manifest.json + run log
uv run python -m pipeline.gmail.corpus                   # data/gmail/raw -> data/gmail/clean
uv run python -m tools.slack_profile                     # corpus counts -> data/slack/profile.json (also tools.gmail_profile)
```

There is no linter or build step. Tests use plain `unittest`. Each test module does `sys.path.insert(0, ROOT)`, and most also run their module's doctests with `doctest.testmod(module)`, so the doctests in a module's docstring count as tests.

## Data

`data/` is gitignored and, in a worktree, is a symlink to the main checkout's `data/`. Tests that need the real corpus are marked `@unittest.skipUnless(<dir>.is_dir(), ...)`. `tests/golden/*_fingerprint.json` hold one sha256 over a whole corpus output, so any byte change to a clean or markdown file fails a golden. Every refactor has to keep the goldens and the manifest sha256 values unchanged. A deliberate output change updates the golden in the same PR, with the new count in the commit message (see the recent `pins N messages` commits).

## Architecture

- **One pipeline per source, no coupling.** `pipeline/` (top level) is Confluence. `pipeline/slack/` and `pipeline/gmail/` (Linear is planned) import nothing from each other or from the Confluence modules. The only shared module is `pipeline/observability.py`: LlamaIndex instrumentation events (`FileCleaned`, `FileFailed`, `StageDone`) on the root dispatcher, written to a JSON-lines run log by `events_logged_to(path)`. A new source adds a `source=` value, not a new module. Status goes in events, never in `print`.
- **Staged, pure functions.** Each module is one stage and one idea: a pure function from text to a NamedTuple result, e.g. Slack: `unescape` → `normalize_whitespace` → `corpus.write_clean_corpus` → `channel_of` / `split_messages` / `parse_speaker` → `parse_thread` → `Thread`. Corpus writers write `<source>/clean/` plus a `_manifest.json` with one row per file (sha256 and the counts that stage owns).
- **LlamaIndex first.** Use library components (`MarkdownNodeParser`, `SentenceSplitter`, `IngestionPipeline`). Custom logic goes in only as a NodeParser/TransformComponent wrapper, never as a custom chunker. For Confluence, `to_markdown` rewrites every heading style (markdown-it plus our own label rule for bare `Overview:` lines) as `#`, keeping the same line count, so line ranges stay valid for citations.
- **Truth sets.** Hand-decided expectations on real files live in `tests/fixtures/headings/expected.json` (Confluence headings) and `tests/fixtures/slack_truth/expected.json` (Slack message starts). A rule change has to keep truth-set precision.
- `buckets.py`, `headings.py`, `blocks.py` are retired heading detectors, and `archive/v0/` is the first monolithic version. Don't build on them.

## Story workflow

All work is driven by stories. The rules, template, glossary and index are in `docs/stories.md`, and the stories themselves are in `docs/stories/<n>-<stage>.md` (IDs `PARSE-n`, `GMAIL-n`, `LINEAR-n`, `SLACK-n`). One story = one function = one small PR (about 60 lines including tests), done TDD (red tests first). Every module opens with a docstring naming its story and the real corpus example that made it necessary, followed by input → output doctests. A rule that can misfire also gets an audit count on the real corpus. The why behind each design is in `docs/design/` (numbered per source: 1-parser, 2-chunker, 3-gmail, 4-linear, 5-slack) and `docs/decisions/`.

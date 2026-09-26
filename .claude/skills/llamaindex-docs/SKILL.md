---
name: llamaindex-docs
description: Look up what LlamaIndex already offers before writing custom logic - every reader, node parser/chunker, metadata extractor, index, store, retriever, postprocessor/reranker, response mode, query/chat engine, agent, workflow, evaluator and observability feature in the official Python docs, plus how to fetch any docs page live. Use when Deepak asks "does LlamaIndex have X", "which parser/retriever/extractor should I use", "list LlamaIndex features/topics", asks what a LlamaIndex class does or when to use it, or when a story is about to add custom logic that a library component might already cover.
---

# LlamaIndex docs lookup

The project rule is **LlamaIndex first**: use a library component, and add custom logic
only as a NodeParser/TransformComponent wrapper. This skill answers "what does the library
already have?" from the official docs, not from memory.

## 1. Start from the local maps

Both files are in the repo, collected from the official docs on 2026-09-25:

- `docs/research/LLAMAINDEX_FEATURE_MAP.md`: grouped summary, with every component class
  name per area (loading, node parsers, extractors, indexes, stores, models, retrievers,
  postprocessors, response synthesis, query/chat engines, routers, agents, workflows,
  evaluation, observability).
- `docs/research/LLAMAINDEX_DOCS_TREE.md`: the full page tree (430 framework pages and
  18 workflow pages), including every LLM, embedding, retriever and vector store
  integration page.

Grep them first (for example `grep -n "Rerank" docs/research/LLAMAINDEX_FEATURE_MAP.md`).
Page URLs are `https://developers.llamaindex.ai/python/framework/<path>/`.

## 2. Go to the live docs for details or anything newer

The docs site has a JSON API (no auth; described in `https://developers.llamaindex.ai/llms.txt`):

```bash
# browse the tree
curl -sL "https://developers.llamaindex.ai/api/list?path=/python/framework/module_guides/&depth=3"
# read one page (paginate with startLine/endLine)
curl -sL "https://developers.llamaindex.ai/api/read?path=/python/framework/module_guides/loading/node_parsers/modules/&startLine=0&endLine=500"
# BM25 search
curl -sL "https://developers.llamaindex.ai/api/search?q=semantic%20chunking&limit=10"
# regex across all docs, e.g. every class ending in NodeParser
curl -sL "https://developers.llamaindex.ai/api/grep?q=NodeParser&max-results=1000"
```

The responses are JSON. Extract the `tree` or `content` field with `python3 -c "import json,sys; ..."`.
Appending `index.md` to any page URL also returns its raw Markdown.

Use the live API when:
- the maps don't name the thing asked about;
- the user needs parameters, defaults or code (the maps list names only);
- the maps may be out of date. If something important changed, offer to refresh both
  files by re-running the `list` and `grep` calls.

## 3. How to answer

- Keep it short: one line per option, then a verdict for **this** project (EnterpriseRAG-Bench:
  closed on-disk corpus of Slack, Gmail, Confluence and Linear; deterministic rule-based
  parsers with golden fingerprints).
- Separate what the docs say from your own recommendation.
- For "when to use / when not" questions, give both lists and a one-line rule of thumb.
- Flag LLM-based components (extractors, LLM rerankers, graph extractors): they cost one
  call per node, aren't deterministic, and must sit in their own cached stage so the
  rule-based goldens stay unchanged.

# LlamaIndex adoption stories

The one place the pipeline touches the framework: the chunking itself (two library node parsers plus our ids and line ranges), and the retrieval experiment that validates the design.

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

---

## PARSE-9  LlamaIndex adapter: the chunker is library code  (split into one function per PR)

**Background for all of PARSE-9**
After PARSE-8 every page is Markdown. This story chains two LlamaIndex node parsers
and adds the three things the framework does not know about our corpus: stable ids,
line ranges, and the breadcrumb as metadata rather than text.

```
markdown file → MarkdownNodeParser → SentenceSplitter(512, overlap 0) → our post-step → TextNodes
                 one node per section     windows the ~2% over budget    id, start/end line,
                 header_path metadata     and heading-less pages         drop heading-only nodes
```

What the framework gives for free and we use as is:
- `MarkdownNodeParser`: cuts at `#` lines, ignores `#` inside ``` fences, sets
  `header_path` like `/Title/Section/`.
- `SentenceSplitter(chunk_size=512, chunk_overlap=0)`: passes small nodes through
  untouched, windows big ones at sentence boundaries. Given the embedder's tokenizer
  it counts the way the embedder does.
- `build_nodes_from_splits`: `SOURCE`, `PREVIOUS`, `NEXT` relationships, metadata
  inheritance from the `Document`.
- `MetadataMode.EMBED` / `text_template`: the breadcrumb goes in front of the text for
  the embedder while `node.text` stays the source lines.

What we add (each its own sub-story):
1. **Stable ids.** Default `id_func` is `uuid4()`. We pass
   `sha256(f"{doc sha256}:{start_line}:{end_line}")`, so an unchanged page gives the
   same ids on every run and the vector store can upsert instead of reload.
2. **Line ranges.** A node's text is contiguous lines of the markdown view, so
   `start_line` = number of newlines before the node's first line in the view, and
   `end_line` = start + lines in the node. Measured 20/20 recovered on every test page.
3. **Heading-only nodes dropped.** A section with no body (11,343 in the corpus) comes
   out as a node whose text is one `#` line. It carries nothing to retrieve; the heading
   still appears in its children's `header_path`.
4. **Metadata contract.** `doc_id`, `title`, `heading_path` (from `header_path`, as a
   list), `start_line`, `end_line`, `sha256`. Line numbers and sha are in both
   exclusion lists so neither embedder nor LLM reads them.

Parent-child ("small to big") is not in this story. `header_path` names each node's
parent section, so a later story can build one parent node per section and
`PARENT`/`CHILD` links without touching chunking. PARSE-16 decides whether it is worth it.

### 1. PARSE-9a  ConfluenceNodeParser chains the two library parsers  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `ConfluenceNodeParser().get_nodes_from_documents([doc])` to return `MarkdownNodeParser` sections trimmed by `SentenceSplitter`, in order
**So that** the pipeline chunks with library code and one call

**Acceptance Criteria (Gherkin)**
- Given the scheduler markdown file as a `Document`, When I call the parser, Then 19 nodes (20 sections minus the heading-only title node), in line order, each `text` starting with its `## ` heading line
- Given a `Document` with one section of 3,000 chars, Then that section yields two or more nodes, each ≤ 512 tokens by the parser's tokenizer, all with the same `header_path`
- Given a `Document` with no `#` at all, Then the nodes are `SentenceSplitter` windows of the whole text
- Given any node, Then `metadata["heading_path"]` is a list starting with the title
- Given `nodes.py`, When I read it, Then it contains no splitting logic, only the two library parsers, the post-step and the metadata mapping

**Example with real data**
Scheduler page, node 1: `text = "## Overview:\n\nThis playbook defines…"`, `heading_path = ["Scheduler Health Oracle and Self‑Heal Procedures", "Overview:"]`.

**Non-functional Requirements**
- Shared NFRs. `nodes.py` is the only module in `pipeline/` allowed to import `llama_index`. About 40 lines.

**Dependencies**
- APIs: `ConfluenceNodeParser(chunk_size: int = 512, tokenizer=None)`; `NodeParser` subclass
- Uses: PARSE-8, `llama_index.core.node_parser.MarkdownNodeParser`, `SentenceSplitter`
- Service Bus: N/A · Database: N/A · UI: N/A

### 2. PARSE-9b  Stable ids and line ranges  ⬜

**Status:** To do

**As a** RAG developer
**I want to** every node to carry `start_line`, `end_line` and an id derived from the file's sha256 and that range
**So that** a rerun over an unchanged page produces identical ids, and a citation names exact lines

**Acceptance Criteria (Gherkin)**
- Given the scheduler markdown file, Then node 1 has `start_line = 2`, `end_line = 6` (exclusive) and `node_id = sha256("<doc sha256>:2:6")`
- Given the same `Document` parsed twice, Then every id is identical
- Given one changed line in the middle of the page, Then only nodes whose text or range changed get new ids
- Given every clean file, Then every node's `[start_line, end_line)` maps back to text equal to the node's text, and the corpus fingerprints to `tests/golden/nodes_fingerprint.json` (id, start, end, path per node)
- Given `start_line`/`end_line`/`sha256`, Then they are in both `excluded_embed_metadata_keys` and `excluded_llm_metadata_keys`

**Example with real data**
Scheduler page: `sha256("dsid_0012a01f…:2:6")` for `Overview:`; `…:6:11` for `Audience:`.

**Non-functional Requirements**
- Shared NFRs. Line lookup is `view.find(first line)` from the previous node's end, so it is linear and unambiguous even when two sections share a first line.

**Dependencies**
- APIs: `id_func(i, doc) -> str` passed to the parser; `line_range(view: str, node_text: str, search_from: int) -> tuple[int, int]`
- Uses: PARSE-9a, PARSE-2b (manifest sha256)
- Service Bus: N/A · Database: N/A · UI: N/A

### 3. PARSE-9c  Breadcrumb as metadata, embed template, heading-only nodes dropped  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `node.text` to be the source lines only, `title` and `heading_path` in metadata, and `get_content(MetadataMode.EMBED)` to start with `"<title> > <section>\n\n"`
**So that** the embedder sees the breadcrumb, the citation shows the author's lines, and nothing is stored twice

**Acceptance Criteria (Gherkin)**
- Given any node, When I call `node.get_content(MetadataMode.EMBED)`, Then it starts with the joined `heading_path` and a blank line, followed by `node.text`
- Given `MetadataMode.LLM`, Then the same prefix; given `MetadataMode.NONE`, Then `node.text` alone
- Given a section with no body, Then no node is produced for it, and its heading still appears in the `heading_path` of the nodes under it
- Given the archived `test_nodes.py`, Then it passes with its breadcrumb assertions pointed at `get_content(MetadataMode.EMBED)`

**Example with real data**
The `Goals` chunk of `typical.md`:
```
node.text                              "## Goals\n- Provide a repeatable acceptance checklist\n- ..."
node.metadata["heading_path"]          ["Telemetry Normalization ...", "Goals"]
node.get_content(MetadataMode.EMBED)   "Telemetry Normalization ... > Goals\n\n## Goals\n- Provide a repeatable ..."
```

**Non-functional Requirements**
- Shared NFRs. `text_template = "{metadata_str}\n\n{content}"`, `metadata_template = "{value}"` on the breadcrumb key only.

**Dependencies**
- APIs: none new; settings on the nodes returned by PARSE-9a
- Uses: PARSE-9a, `llama_index.core.schema.MetadataMode`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-16  Chunking validation: recall@20 on the benchmark questions  ⬜

**Status:** To do

**Background**
The chunker design bets that small section chunks (median ≈ 90 tokens) with a heading
path retrieve better than larger ones, and that sentence-boundary cuts on the 2% of
oversized sections cost nothing measurable; parent-child is the hedge for broad questions. Section 9 of the
[design doc](../design/2-chunker-system-design.md) lays out the evidence for and against.
Only a measurement settles it. EnterpriseRAG-Bench ships 500 questions in
`questions.jsonl`, each with ground-truth documents; 5,189 of the documents are our
Confluence pages. This story is the measurement, restricted to questions whose
ground-truth documents are Confluence pages.

**As a** RAG developer
**I want to** one script that builds three indexes from the same embedder and reports recall@20 per index and per question category
**So that** the chunk size and the parent-child choice are decided by numbers on the benchmark's own questions

**Acceptance Criteria (Gherkin)**
- Given the three variants (A: this design, `markdown_view` → `MarkdownNodeParser` → `SentenceSplitter`; B: A plus a parent node per section from `header_path` and `AutoMergingRetriever`; C: `SentenceSplitter(chunk_size=512)` over the clean text with no headings, the baseline), When I run `tools/validate_chunking.py`, Then I get one table: variant × category → recall@20, plus the overall number
- Given a question, Then recall@20 is 1 if any of the top 20 retrieved nodes has `doc_id` in the question's ground-truth documents, else 0
- Given the run, Then the embedder, its version, the dimension, and the chunk parameters are printed at the top, and the same run twice gives the same table
- Given the result, Then the design doc's section 9 is updated with the table and the chosen default in the same PR
- Given "Info Not Found" and "High Level" questions (no ground truth), Then they are excluded and the count of excluded questions is printed

**Example with real data**
To be filled from the first run; the story records the table verbatim.

**Non-functional Requirements**
- One embed per variant, under $2 each on OpenAI text-embedding-3-large at list price; cache embeddings on disk so a rerun with a different `k` is free.
- Deterministic given the cached embeddings.

**Dependencies**
- Uses: PARSE-9, the benchmark's `questions.jsonl`, one hosted embedder, an in-process vector store (`SimpleVectorStore` is enough at 95k vectors)
- Service Bus: N/A · Database: N/A · UI: N/A

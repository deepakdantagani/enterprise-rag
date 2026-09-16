# LlamaIndex adoption stories

The one place the pipeline touches the framework: chunks become `TextNode`s, plus the retrieval experiment that validates the chunk design.

Shared rules, the story template and the glossary are in [stories.md](../stories.md); every story here follows them.

---

## PARSE-9  LlamaIndex adapter  ⬜

**Status:** To do

**Background**
PARSE-8 ends with `list[Chunk]`: line ranges plus a `heading_path`, no framework types.
This story is the only place the pipeline touches LlamaIndex. It maps one `Chunk` to one
`TextNode` and nothing else — no chunking rules, no size logic.

Two things the framework already does that the archived v0 adapter did by hand, and that
we do its way this time:

1. **The breadcrumb is metadata, not text.** v0 built `"<title> > <section>\n\n" + body`
   and stored that in `node.text`. LlamaIndex instead injects metadata into the text at
   read time: `node.get_content(MetadataMode.EMBED)` and `MetadataMode.LLM` render
   `text_template` with the metadata that is not excluded, while `node.text` stays the
   exact source lines. Doing it v0's way means the breadcrumb is welded into the stored
   text, cannot be excluded from the LLM but kept for the embedder, and is counted twice
   once metadata rendering is on. So: `text` is the body, `heading_path` and `title` are
   metadata, and `text_template` puts them back in front for the embedder.

2. **Nodes come from `build_nodes_from_splits`.** `llama_index.core.node_parser.node_utils.build_nodes_from_splits(splits, doc, id_func=self.id_func)`
   wires the `SOURCE` relationship back to the `Document`, the `PREVIOUS`/`NEXT` links
   between neighbours, metadata inheritance and node ids. v0 constructed `TextNode(...)`
   directly and set only `SOURCE`, so prev/next were missing. We keep the per-chunk
   metadata by setting it on the returned nodes.

Both are settings on `TextNode`, which is `Document`'s base class — the same
`excluded_embed_metadata_keys` / `excluded_llm_metadata_keys` the loader already uses.

Three more things the [chunker design](../design/2-chunker-system-design.md) puts here:

3. **Ids are stable.** LlamaIndex's default `id_func` is `uuid4()`, so a rerun gives
   new ids and the vector store cannot tell "unchanged" from "new". We pass
   `id_func = sha256(f"{doc sha256}:{start}:{end}")`. Same bytes, same range, same id.
4. **Parent nodes.** Every chunk carries `section_line` and `parent_line`. For each
   section that has children, the adapter builds one parent `TextNode`, id
   `sha256(f"{doc sha256}:section:{line}")`, text = its own body plus its children in
   order, stored in the docstore only and never embedded. Each chunk gets a `PARENT`
   relationship to it and the parent a `CHILD` to each chunk. `AutoMergingRetriever`
   uses these to return a whole section when most of its children match.
5. **Relationships are for retrieval, not embedding.** `SOURCE`, `PREVIOUS`, `NEXT`
   come from `build_nodes_from_splits`; `PARENT`/`CHILD` from point 4. None of them is
   in the embed text. Only `title` and `heading_path` are.

**As a** RAG developer
**I want to** a `NodeParser` that wraps the chunker and produces `TextNode`s
**So that** the pipeline plugs into LlamaIndex without the chunker depending on it

**Acceptance Criteria (Gherkin)**
- Given a `Document`, When I call `ConfluenceNodeParser().get_nodes_from_documents([doc])`, Then each node's `text` is the chunk's source lines only, with no breadcrumb prefix
- Given the same nodes, When I call `node.get_content(MetadataMode.EMBED)`, Then it starts with `"<title> > <section>\n\n"`
- Given the same nodes, Then metadata has `line_start`, `line_end`, `heading_path`, and `line_start`/`line_end` are in both exclusion lists so neither the embedder nor the LLM reads line numbers
- Given two consecutive nodes from one `Document`, Then each has a `SOURCE` relationship to that document, and the first has `NEXT` to the second and the second `PREVIOUS` to the first
- Given the same `Document` parsed twice, Then every node id is identical between the two runs; given one changed line, Then only the chunks whose `[start, end)` moved or changed get new ids
- Given the playbook fixture, When I parse it, Then the three `### A/B/C` chunks each have a `PARENT` relationship to one node whose text is their three bodies in order, that node has three `CHILD` relationships, and it is in the returned docstore nodes but excluded from the embed list
- Given any node, When I call `node.get_content(MetadataMode.EMBED)`, Then it contains no ids, line numbers or relationship fields, only the path and the text
- Given `nodes.py`, When I read it, Then it contains no chunking rules, only the mapping `Chunk -> TextNode`
- Given the archived `test_nodes.py`, Then it passes with its two breadcrumb assertions re-pointed from `node.text` to `node.get_content(MetadataMode.EMBED)`; every other assertion unchanged

**Example with real data**
The `Goals` chunk of `typical.md`, which v0 asserted on:
```
node.text                              "- Provide a repeatable acceptance checklist\n- ..."
node.metadata["title"]                 "Telemetry Normalization and Fidelity Acceptance Playbook for Enterprise Tenants"
node.metadata["heading_path"]          ["Telemetry Normalization ...", "Goals"]
node.get_content(MetadataMode.EMBED)   "Telemetry Normalization ... > Goals\n\n- Provide a repeatable ..."
```
The last line is byte-for-byte what v0 stored in `text`; only where it lives changed.

**Non-functional Requirements**
- Shared NFRs at the top of this file (deterministic, behaviour-preserving, readable).
- `nodes.py` is the only module in `pipeline/` allowed to import `llama_index`.
- Node ids come from the parser's `id_func`, so a rerun over unchanged input gives the same ids.

**Dependencies**
- APIs: `ConfluenceNodeParser(max_chars=2048)`; `parse_nodes(...) -> (leaf_nodes, parent_nodes)` so the caller embeds leaves and stores both
- Uses: PARSE-6, PARSE-7, PARSE-8 (incl. 8h `parent_lines`); `llama_index.core.node_parser.NodeParser`, `build_nodes_from_splits`, `llama_index.core.schema.MetadataMode`, `NodeRelationship.PARENT/CHILD`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## PARSE-16  Chunking validation: recall@20 on the benchmark questions  ⬜

**Status:** To do

**Background**
The chunker design bets that small section chunks (median ≈ 90 tokens) with a heading
path retrieve better than larger ones, and hedges with parent-child. Section 9 of the
[design doc](../design/2-chunker-system-design.md) lays out the evidence for and against.
Only a measurement settles it. EnterpriseRAG-Bench ships 500 questions in
`questions.jsonl`, each with ground-truth documents; 5,189 of the documents are our
Confluence pages. This story is the measurement, restricted to questions whose
ground-truth documents are Confluence pages.

**As a** RAG developer
**I want to** one script that builds three indexes from the same embedder and reports recall@20 per index and per question category
**So that** the chunk size and the parent-child choice are decided by numbers on the benchmark's own questions

**Acceptance Criteria (Gherkin)**
- Given the three variants (A: this design, small chunks; B: A plus `AutoMergingRetriever`; C: `SentenceSplitter(chunk_size=512)` over whole pages as the baseline), When I run `tools/validate_chunking.py`, Then I get one table: variant × category → recall@20, plus the overall number
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

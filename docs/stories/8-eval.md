# Eval stories

How we score retrieval on EnterpriseRAG-Bench, across every source. Rules and template:
[stories.md](../stories.md).

Why this comes first: the plan is a naive baseline (every document, `SentenceSplitter(512)`,
a local embedder, no cleaning) and then one clean-up story at a time. A clean-up story is
only worth merging if it moves a number, so the number has to exist before the baseline.

LlamaIndex first: the scoring is LlamaIndex's `RetrieverEvaluator` and its metrics
(`hit_rate`, `recall`, `mrr`, `ndcg`). Our code is only what it lacks: scoring documents
instead of chunks (EVAL-1), reading the benchmark's questions (EVAL-2a) and grouping the
results by question type and source (EVAL-2b). LlamaIndex 0.14 has no dataset runner, so a
run is a plain loop of `evaluator.evaluate(question, expected_ids)`.

Eval glossary:

- **Question**: one row of `questions.jsonl` (500 rows). Fields: `question_id`,
  `question_type` (10 types), `source_types`, `question`, `expected_doc_ids`, `gold_answer`,
  `answer_facts`.
- **Expected docs**: `expected_doc_ids`, the `dsid_…` documents the answer comes from. 377
  questions expect 1, 93 expect 2 to 10, and 30 expect none (all 20 `info_not_found` and all
  10 `high_level`).
- **Document recall**: the leaderboard's retrieval metric. For one question, the share of its
  expected docs that appear in what we retrieved; averaged over questions. The leaderboard
  ranks on an LLM-judged answer score, with document recall as a tie-break; we can compute
  recall locally, with no model, so it is our inner-loop number.
- **Top k documents**: a retriever returns chunks, and several chunks can come from one
  document. We score the first `k` **distinct** documents in rank order, so a document split
  into many chunks cannot crowd out the rest or count twice. Default `k = 10`.

| Story | Status |
|---|---|
| EVAL-1  `DocumentRetrieverEvaluator` | ✅ |
| EVAL-2a  `load_questions` | ✅ |
| EVAL-2b  `metrics_report`: overall, per question type, per source, at k = 5, 10, 20 | ✅ |
| EVAL-3a  `parquet_documents` | ✅ |
| EVAL-3b  `baseline_pipeline`: `SentenceSplitter(512)` + embedder into a vector store | ✅ |
| EVAL-3c  `score_retriever`: every question × k in one event loop | ✅ |
| EVAL-3d  `python -m pipeline.eval.baseline`: sample run, then the full run | ⬜ |
| EVAL-4  `trace_to_phoenix`: see each question's retrieval in Arize Phoenix | ✅ |

---

## EVAL-1  `DocumentRetrieverEvaluator`  ✅

**Status:** Done

**As a** RAG developer
**I want to** LlamaIndex's `RetrieverEvaluator` to score the first `top_k_docs` distinct
source documents instead of chunk ids
**So that** every index we build is scored the way the leaderboard scores it, with library
metrics

**Acceptance Criteria (Gherkin)**
- Given chunks from docs `[a, a, a, b]` and `top_k_docs = 2`, Then `retrieved_ids` is `[a, b]`
  and recall for expected `[b]` is 1.0: chunks of one document take one place
- Given docs `[a, b, c]`, `top_k_docs = 2` and expected `[c]`, Then recall 0.0: `c` is third
- Given docs `[a]` and expected `[a, b]`, Then recall 0.5
- Given chunks `[a, a, a, b]` and expected `[b]`, Then mrr 0.5: `b` is the 2nd document even
  though it is the 4th chunk
- Given chunks `[a, b, a]`, Then `retrieved_texts` holds each document's best chunk once
- Given `top_k_docs = 0`, Then a validation error
- Given a chunk with no source document, Then `ValueError` naming the chunk: it cannot be
  scored, and dropping it silently would hide a broken index

**Example with real data**
`qst_0431` (completeness): "What is the procedure for an emergency rollback of a Serving
Runtime release (Hosted and Dedicated)?" expects `dsid_f6e3b7ad…` "Emergency rollback:
Serving Runtime (Hosted + Dedicated)" (4,429 chars, several chunks at 512 tokens) and
`dsid_840703a1…` "Runtime release pipeline: rollback procedure". A retriever whose top 10
documents hold only the first scores recall 0.5 on it.

**Non-functional Requirements**
- Shared NFRs. No network, no model: the tests use a fixed retriever, the doctest a
  `SummaryIndex`.
- Reuse: `RetrieverEvaluator` and its metrics unchanged; the override is its one hook,
  `_aget_retrieved_ids_and_texts`. A node postprocessor could not do this, because the
  evaluator reads `node_id`, and a chunk's `node_id` is never a dsid.
- Replaces the first version of this story (`document_recall`, a function around `Recall`),
  which re-did what the evaluator already does.

**Dependencies**
- APIs: `DocumentRetrieverEvaluator.from_metric_names(names, retriever=..., top_k_docs=10)`
  in `pipeline/eval/evaluator.py`; each node's `ref_doc_id` must be its dsid, so EVAL-3
  builds `Document(id_=doc_id)`
- Uses: `llama_index.core.evaluation.RetrieverEvaluator`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## EVAL-2a  `load_questions`  ✅

**Status:** Done

**As a** RAG developer
**I want to** `load_questions(path)` to return the benchmark questions that have expected
docs, as small typed records, and say how many it left out
**So that** every run scores the same 470 questions, and a changed answer key fails a test

**Acceptance Criteria (Gherkin)**
- Given a line with expected docs, Then a `Question(question_id, question_type,
  source_types, text, expected_doc_ids)`
- Given a line with no expected docs, Then it is left out and counted in `skipped`
- Given the real file, Then 470 questions and 30 skipped, and the file's sha256 is
  `f9524b91…d3d147905` (a golden: a new release of the answer key fails it on purpose)

**Example with real data**
`qst_0431` → `Question("qst_0431", "completeness", ("confluence",), "What is the procedure
for an emergency rollback…", ("dsid_f6e3b7ad…", "dsid_840703a1…"))`. `qst_0471`
(`info_not_found`, no expected docs) → skipped.

**Non-functional Requirements**
- Shared NFRs. Reads one file; no network. `gold_answer` and `answer_facts` are not loaded:
  they belong to answer scoring, not retrieval.
- The file moves to `data/_full/questions.jsonl`, beside `documents.parquet` (it was under
  `data/linear/` only because the Linear work downloaded it; it covers every source).

**Dependencies**
- APIs: `load_questions(path) -> LoadedQuestions(questions: list[Question], skipped: int)` in
  `pipeline/eval/questions.py`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## EVAL-2b  `metrics_report`  ✅

**Status:** Done

**As a** RAG developer
**I want to** one table of mean `hit_rate`, `recall`, `mrr`, `ndcg` at k = 5, 10 and 20,
overall, per question type and per source
**So that** a run says not only how good retrieval is but where it fails

**Acceptance Criteria (Gherkin)**
- Given evaluation results for each question and k, Then one row per (group, k) with the
  mean of each metric and the number of questions in the group
- Given a question with two source types, Then it counts in both source groups: 68 of the
  470 questions span 2 to 5 sources, so source rows add up to more than 470
- Given recall@20 well above recall@10 for a group, Then that group's docs are found but
  ranked too low (a ranking problem, not a missing-document problem)

**Example with real data**
Group sizes on the real file: overall 470; by source confluence 114, jira 100, slack 79,
github 60, google_drive 60, linear 58, gmail 55, hubspot 34, fireflies 25; by type basic
175, semantic 125, intra_document_reasoning 40, project_related 40, constrained 30,
conflicting_info 20, completeness 20, miscellaneous 20.

**Non-functional Requirements**
- Shared NFRs. Pure: results in, rows out. Writing a run's files is EVAL-3.

**Dependencies**
- APIs: `metrics_report(scored: Iterable[Scored(question, k, metrics)]) -> list[ReportRow(group, k, questions, means)]`
  in `pipeline/eval/report.py`; groups are `overall`, `type:<question_type>`, `source:<source_type>`
- Uses: EVAL-1's `RetrievalEvalResult.metric_vals_dict`, EVAL-2a's `Question`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## EVAL-4  `trace_to_phoenix`  ✅

**Status:** Done

**As a** RAG developer
**I want to** every LlamaIndex call of an eval run traced to a local Arize Phoenix UI
**So that** when a group scores low I can open one question and see what the retriever
returned, instead of guessing

**Acceptance Criteria (Gherkin)**
- Given `trace_to_phoenix(tracer_provider=provider)` and an evaluation, Then the provider
  receives a span of kind `RETRIEVER`
- Given that span, Then it holds the question (`input.value`) and each retrieved chunk's text
  (`retrieval.documents.<i>.document.content`)
- Given no provider, Then spans go to the Phoenix server at `localhost:6006`, project
  `enterprise-rag-eval`, over HTTP
- Given an embedding call, Then its span keeps the text but the vector is `__REDACTED__`: in
  the first sample run (207 docs, 822 chunks) the 1,024-number vectors pushed one export batch
  to 12 MB, over the 4 MB Phoenix accepts over gRPC, and those traces were lost

**Example with real data**
To be filled by EVAL-3's first run: qst_0431 opened in Phoenix, with its top chunks and the
documents they came from.

**Non-functional Requirements**
- Shared NFRs. The tests use an in-memory span exporter: no server, no network.
- Reuse: no span is written by our code. OpenInference's `LlamaIndexInstrumentor` hooks
  LlamaIndex's instrumentation dispatcher, the same one `pipeline/observability.py` listens
  to; the function only chooses where spans go.
- Dependency discipline: two new runtime dependencies, `openinference-instrumentation-llama-index`
  4.5.2 and `arize-phoenix-otel` 0.17.1 (resolve with the pinned `llama-index-core` 0.14.24,
  no other pin moves). The Phoenix server itself is not a dependency: it runs on demand with
  `uv run --with arize-phoenix phoenix serve`. Considered and not taken: Langfuse (a server to
  host), MLflow (weaker per-question view).

**Dependencies**
- APIs: `trace_to_phoenix(project="enterprise-rag-eval", tracer_provider=None) -> TracerProvider`
  in `pipeline/eval/tracing.py`
- Uses: `openinference.instrumentation.llama_index.LlamaIndexInstrumentor`, `phoenix.otel.register`
- Service Bus: N/A · Database: N/A · UI: Arize Phoenix at `http://localhost:6006` (local)

---

## EVAL-3  The naive baseline (3a–3d)

Every document from `documents.parquet`, no cleaning, `SentenceSplitter(chunk_size=512,
chunk_overlap=50)`, `qwen3-embedding:0.6b` on Ollama (1,024 dimensions, ~150 chunks/s measured
on this Mac), Qdrant as the vector store, then the 470 questions scored with EVAL-1 and 2b and
traced with EVAL-4. Estimated ~1.3M chunks and ~2.5 h of embedding for the full corpus.

Decisions:
- **Splitter: `SentenceSplitter`.** LlamaIndex's default, so the baseline is the plain
  default. Smarter parsers are what the per-source stories must prove against it.
- **Vector store: Qdrant** (Docker, `localhost:6333`, data under `data/_index/qdrant/`).
  Chosen over LanceDB for native hybrid (dense + sparse) search later and a managed version
  for AWS. Docker has 8.3 GB of memory here and the full-precision vectors are ~5.3 GB, so the
  full run keeps vectors on disk with an int8 copy in memory (decided in 3d).

What the first sample run found (3 single-source questions + 20 other docs per source: 207
documents → 822 chunks, ~50 s; recall@10 0.96 over 27 questions, all `basic`; inflated, as the
haystack is 207 docs, not 511,962):
1. 497 titles hold a whole body (493 Slack, 3 Confluence, 1 Google Drive; longest 10,693
   chars) and `SentenceSplitter` counts embedded metadata against the chunk → only `content`
   is embedded (3a).
2. Span batches with embedding vectors reached 12 MB, over Phoenix's 4 MB → vectors redacted,
   spans over HTTP (EVAL-4).
3. The evaluator retrieves async, so `QdrantVectorStore` needs `aclient=AsyncQdrantClient(...)`
   (3d).
4. `evaluate()` opens a new event loop per call and the async Qdrant client is bound to the
   first one → all questions are scored inside one loop with `aevaluate` (3c).

## EVAL-3a  `parquet_documents`  ✅

**Status:** Done

**As a** RAG developer
**I want to** `parquet_documents(path, batch_size)` to yield the corpus as batches of LlamaIndex
`Document`s, one per row, unchanged
**So that** the baseline reads all 511,962 documents without holding 2.46B chars at once, and
every chunk can be traced back to its dsid

**Acceptance Criteria (Gherkin)**
- Given 5 rows and `batch_size = 2`, Then batches of 2, 2, 1 in file order
- Given a row, Then `Document(id_=doc_id, text=content, metadata={source_type, title})`
- Given any document, Then its embedded and LLM text is the content alone
- Given the real file, Then 511,962 rows, and the first document is
  `dsid_e54ef48b…` "Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod)"

**Example with real data**
`dsid_c655aa63…` (Confluence) has a 10,693-char title that is the page's whole body. With the
title embedded, `SentenceSplitter(512)` raised "Metadata length (1864) is longer than chunk
size (512)"; with only the content embedded it splits like any other page.

**Non-functional Requirements**
- Shared NFRs. No cleaning of any kind: that is the point of the baseline.
- Reuse: `pyarrow.parquet.ParquetFile.iter_batches` for the batching. LlamaIndex's
  `PandasParquetReader` (llama-index-readers-file) was not taken: it loads the whole file and
  writes every column into the text. New dependency: `pyarrow==25.0.1`.
- The file is one row group, so pyarrow decompresses it whole on first read (~3 GB of memory);
  fine on this 64 GB Mac.

**Dependencies**
- APIs: `parquet_documents(path, batch_size=1000) -> Iterator[list[Document]]` in
  `pipeline/eval/documents.py`
- Service Bus: N/A · Database: N/A · UI: N/A

## EVAL-3b  `baseline_pipeline`  ✅

**Status:** Done

**I want to** `baseline_pipeline(embed_model, vector_store, docstore)` to return the one
`IngestionPipeline([SentenceSplitter(512, 50), embed_model], vector_store=..., docstore=...)`
**So that** the baseline is library code only, and a re-run after a crash skips documents
already embedded (the docstore keeps each document's hash; `DocstoreStrategy.UPSERTS`)

- Given the pipeline, Then its first step is `SentenceSplitter(chunk_size=512, chunk_overlap=50)`
- Given a long and a short page and `MockEmbedding`, Then more than two chunks, each embedded,
  each with `ref_doc_id` = its dsid, and every one of them in the vector store
- Given the same documents run twice, Then the second run returns no chunks and embeds nothing
- Reuse: all LlamaIndex; the function is the declaration. Verified before writing: with a
  docstore, `IngestionPipeline` defaults to `DocstoreStrategy.UPSERTS` and skips unchanged
  documents
- File: `pipeline/eval/baseline.py`; tests with `SimpleVectorStore` and `SimpleDocumentStore`,
  no model, no network

## EVAL-3c  `score_retriever`  ✅

**Status:** Done

**I want to** `score_retriever(retriever, questions, ks=(5, 10, 20))` to return one `Scored`
per question and k, all inside one event loop (`aevaluate`)
**So that** EVAL-2b can report it, and async vector stores such as Qdrant work (finding 4)

- Given 2 questions and ks (2, 10), Then 4 `Scored` rows, question-major, with recall and mrr on
  the top k documents
- Given a retriever that, like Qdrant's async client, fails outside the loop it was first used
  in, Then all 6 evaluations (2 questions × 3 k) succeed; the old per-call `evaluate()` fails it
- Every row carries `hit_rate`, `recall`, `mrr`, `ndcg`
- File: `pipeline/eval/score.py`; no model, no network

## EVAL-3d  `python -m pipeline.eval.baseline`  ⬜

**Status:** To do

**I want to** one command that wires 3a → 3b → Qdrant → 3c → 2b with Phoenix tracing, with
`--sample` (the 207-document run above) and the full run
**So that** the baseline is one reproducible command, and its result is the first row of
`docs/eval/results.md`

- New dependencies: `llama-index-embeddings-ollama==0.10.0`,
  `llama-index-vector-stores-qdrant==0.10.3` (resolve with `llama-index-core` 0.14.24)
- Writes `runs/<date>-baseline/metrics.json` (gitignored) and one row of `docs/eval/results.md`

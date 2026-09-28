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
| EVAL-3d1  `embedded_doc_ids`: resume from what Qdrant already holds | ✅ |
| EVAL-3d2  `sample_corpus`: 27 questions, 207 documents from all 9 sources | ✅ |
| EVAL-3d3  `ingest_corpus` + `python -m pipeline.eval.baseline --sample` | ✅ |
| EVAL-3f  `--embed`: choose the embedder; voyage-4 chosen | ✅ |
| EVAL-3g  skip blank documents | ✅ |
| EVAL-3h  precision in the report | ✅ |
| EVAL-3e  the full run (v0): 511,957 documents, 470 questions, recall@10 0.609 | ✅ |
| EVAL-4  `trace_to_phoenix`: see each question's retrieval in Arize Phoenix | ✅ |
| EVAL-5a  `write_run`: every run's metrics and per-question scores kept in git | ✅ |
| EVAL-5b  `results_tables`: `results.md` tables generated from the runs | ✅ |
| EVAL-5c  `html_report`: the interactive report, generated and published | ✅ |

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
- Given a retrieval of 50 chunks, Then its span keeps every chunk, the best-ranked included: a
  span holds up to 1,024 attributes (`phoenix_provider`); OpenTelemetry's default of 128 dropped
  the first chunks in the first `--sample` run ("Attributes dict is full")

**Example with real data**
To be filled by EVAL-3's first run: qst_0431 opened in Phoenix, with its top chunks and the
documents they came from.

**Non-functional Requirements**
- Shared NFRs. The tests use an in-memory span exporter: no server, no network.
- Reuse: no span is written by our code. OpenInference's `LlamaIndexInstrumentor` hooks
  LlamaIndex's instrumentation dispatcher, the same one `pipeline/observability.py` listens
  to; the function only chooses where spans go.
- Dependency discipline: two runtime dependencies, `openinference-instrumentation-llama-index`
  4.5.2 and `opentelemetry-exporter-otlp-proto-http` 1.45.0 (resolve with the pinned
  `llama-index-core` 0.14.24). EVAL-4b dropped `arize-phoenix-otel`: its
  `register(protocol="http/protobuf")` raises AttributeError on the exporter's `_headers` with
  the current OpenTelemetry exporter, so the provider is plain OpenTelemetry (a `Resource` with
  `openinference.project.name`, a `BatchSpanProcessor`, an OTLP HTTP exporter to
  `localhost:6006/v1/traces`). A test now takes that default path, and a live check sent a span
  to the running Phoenix. The Phoenix server itself is not a dependency: it runs on demand with
  `uv run --with arize-phoenix phoenix serve`. Considered and not taken: Langfuse (a server to
  host), MLflow (weaker per-question view).

**Dependencies**
- APIs: `trace_to_phoenix(project="enterprise-rag-eval", tracer_provider=None) -> TracerProvider`
  in `pipeline/eval/tracing.py`
- Uses: `openinference.instrumentation.llama_index.LlamaIndexInstrumentor`, OpenTelemetry's `OTLPSpanExporter` (HTTP)
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
  for AWS. Docker had 8.3 GB of memory and the full-precision vectors are ~5.3 GB (estimated);
  decided: raise Docker Desktop to 16 GB and keep every vector in memory at full precision
  (no quantization), so the baseline's search is exact.
- **Resume: skip the dsids already in Qdrant** (3d1), not the IngestionPipeline docstore:
  at 511,962 documents a `SimpleDocumentStore` is a ~2.5 GB JSON file rewritten per batch.

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

## EVAL-3d1  `embedded_doc_ids`  ✅

**Status:** Done

**I want to** `embedded_doc_ids(client, collection_name)` to return the dsids already stored
in the Qdrant collection (the `ref_doc_id` of every chunk, read with `scroll`, no vectors)
**So that** a stopped full run resumes by dropping those documents, with no extra file

- Given a long page (several chunks) and a short one ingested, Then `{dsid_a, dsid_b}`
- Given `page_size = 1`, Then the same set: it pages through every chunk
- Given a collection not created yet, Then the empty set
- Known gap: uploads go 64 chunks at a time, so a crash mid-upload can leave the last batch's
  documents half-written and skipped; at most one batch of 1,000. 3d2 logs the batch in flight
- File: `pipeline/eval/resume.py`; tests on `QdrantClient(":memory:")`, no Docker. New
  dependency: `llama-index-vector-stores-qdrant==0.10.3` (brings `qdrant-client` 1.19.1)

## EVAL-3d2  `sample_corpus`  ✅

**Status:** Done

**I want to** `sample_corpus(questions, doc_sources, questions_per_source=3, others_per_source=20, seed=0)`
to pick, per source, its first single-source questions, their expected documents and a few
random other documents from that source
**So that** `--sample` runs the whole baseline in about a minute before the ~2.5 h full run

- Given questions from two sources, Then the first single-source ones of each, sources in
  alphabetical order; a question with two sources is never picked
- Given `others_per_source = 2`, Then every expected document plus 2 others per source
- Given the same seed, Then the same sample
- Given the real files, Then 27 questions and 207 documents across all 9 sources, the first
  sample run's corpus (822 chunks, recall@10 0.96; inflated, the haystack is 207 documents)
- File: `pipeline/eval/sample.py`; pure

## EVAL-3d3  `ingest_corpus` + `python -m pipeline.eval.baseline`  ✅

**Status:** Done

**As a** RAG developer
**I want to** one command that loads (3a), splits and embeds (3b) into Qdrant, resuming from
what Qdrant holds (3d1), then scores every question (3c) into the report (2b), traced to
Phoenix (EVAL-4), with `--sample` for the 207-document corpus (3d2)
**So that** the baseline is one reproducible command whose output is a row on the scoreboard

**Acceptance Criteria (Gherkin)**
- Given 5 documents, Then `ingest_corpus` embeds all 5 and returns 5
- Given `skip_doc_ids = {dsid_1, dsid_2}`, Then only the other 3 are embedded
- Given `keep_doc_ids = {dsid_0, dsid_4}`, Then only those 2 are embedded
- Given batches of 2, Then one `StageDone` per batch with the number of documents embedded
- Given `events_logged_to(path, only=PipelineEvent)`, Then LlamaIndex's own events (whose
  embedding events carry every vector, ~25 GB estimated on the full run) are not logged
- Given `python -m pipeline.eval.baseline --sample` against Ollama, Qdrant and Phoenix, Then
  it finishes and writes `runs/<date>-baseline_sample/metrics.json` and `events.jsonl`
- Given the same command again, Then it embeds nothing and reports the same numbers

**Example with real data** (run on 2026-09-26)
First run: 207 documents → 832 chunks in collection `baseline_sample`, 57 s; 512 `StageDone`
lines (one per 1,000-row batch). Overall at k = 10: hit_rate 0.963, recall 0.963, mrr 0.854,
ndcg 0.880 over 27 `basic` questions; Slack is the weakest source (recall 0.667 at every k).
Re-run: 7 s, 0 documents embedded, 832 chunks, identical numbers. The sample proves the
wiring; its recall is inflated (a 207-document haystack) and is not the baseline.

**Non-functional Requirements**
- Shared NFRs. `ingest_corpus` is tested with `SimpleVectorStore` and `MockEmbedding`; the
  command is proven by the run above (it needs Ollama, Qdrant and Phoenix).
- Scoring is not in `ingest_corpus`: a retriever needs a vector store that keeps text, which
  `SimpleVectorStore` does not; the command builds it from Qdrant and calls 3c.
- `baseline_pipeline`'s docstore becomes optional (default none): resume is 3d1's job.
- New dependency: `llama-index-embeddings-ollama==0.10.0`. `runs/` is gitignored.
- Shared module change: `events_logged_to` gains `only=` (default: every event, as before).

**Dependencies**
- APIs: `ingest_corpus(documents_path, vector_store, embed_model, skip_doc_ids, keep_doc_ids, batch_size) -> int`
  and `main()` in `pipeline/eval/baseline.py`; `events_logged_to(path, only=BaseEvent)` in
  `pipeline/observability.py`
- Service Bus: N/A · Database: Qdrant (Docker, `localhost:6333`) · UI: Phoenix (`localhost:6006`)

## EVAL-3f  `--embed`: choose the embedder  ✅

**Status:** Done

**As a** RAG developer
**I want to** `python -m pipeline.eval.baseline --embed <model>`, each embedder into its own
Qdrant collection, voyage-4 the only one kept
**So that** the full run is not ~20 h on this Mac, and the embedder is chosen on our questions

**Why** (measured 2026-09-26): `qwen3-embedding:0.6b` runs at ~22 chunks/s here, the same
through Ollama and through PyTorch on MPS, at any batch size or number of parallel requests;
the GPU is ~95% busy (macOS `ioreg`), so one 512-token chunk already fills it. The full corpus
is ~1.56M chunks (3.05 per document on 500 random documents) → ~20 h.

**Acceptance Criteria (Gherkin)**
- Given `voyage-4`, Then a `VoyageEmbedding` at 1,024 dimensions; given any other name
  (including the removed `qwen3-embedding:0.6b`), Then an error listing the known ones
- Given an embedder and `--sample` or not, Then its own collection, e.g.
  `baseline_sample__voyage_4`: vectors of two models are never mixed
- `VOYAGE_API_KEY` is read from `.env` (gitignored), never from the command line

**Example with real data** (`--sample`, 27 questions, 207 documents)

| embedder | dims | recall@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|
| qwen3-embedding:0.6b (local) | 1,024 | 0.963 | 0.854 | 0.880 |
| voyage-4 | 256 | 1.000 | 0.878 | 0.909 |
| voyage-4 | 512 | 1.000 | 0.917 | 0.938 |
| voyage-4 | 1,024 | 1.000 | 0.935 | 0.952 |
| voyage-4 | 2,048 | 1.000 | 0.935 | 0.952 |

27 easy questions, so a signal, not proof. Decided: **voyage-4 at 1,024** for the baseline
(2,048 adds nothing here; same size as the local model, so the same Qdrant memory).

Measured cost and speed for the full corpus: 1,000 random documents are 1,305,021 voyage-4
tokens (0.270 per character, overlap included) → ~665M tokens → ~$40 at $0.06 per 1M, ~$28
after the account's 200M free voyage-4 tokens. One request at a time runs at 126 chunks/s
(~3.1M tokens per minute, the account's cap is 8M) → ~3.4 h. Splitting alone is 4,389 chunks/s.
`voyage-4-large` (+4.8% retrieval in Voyage's own benchmark, $0.12 per 1M, 3M TPM cap) is left
as a later experiment against this baseline.

**Non-functional Requirements**
- New dependencies: `llama-index-embeddings-voyageai==0.7.0` and `voyageai==0.5.0` for Python ≥
  3.13 (the integration declares its client only below 3.13, so on 3.14 it was missing)
- The local path is removed (Deepak's call, 2026-09-26): `llama-index-embeddings-ollama` is no
  longer a dependency, and its Qdrant collections, the Ollama model in memory and the
  downloaded HuggingFace weights (1.1 GB) were deleted. The measurements above stay as the
  reason; the local model is one row in `EMBEDDERS` away if it is ever needed again
- Files: `pipeline/eval/embedders.py`, `--embed` in `pipeline/eval/baseline.py`

## EVAL-3g  Skip blank documents  ✅

**Status:** Done

**As a** RAG developer
**I want to** `parquet_documents` to skip a row whose content is blank
**So that** the full run does not stop on a document that has nothing to embed

**Acceptance Criteria (Gherkin)**
- Given rows with content `""` and `" \n "`, Then no Document is yielded for them, and batch
  boundaries stay those of the file (a batch may come out shorter)
- Given the real file, Then batch 279 holds 999 Documents and not `dsid_33cbedf0…`

**Example with real data**
The full voyage-4 run stopped at batch 279 (279,000 documents, 1,080,790 chunks in Qdrant) with
`voyageai.error.InvalidRequestError: Input cannot contain empty strings`. The cause is
`dsid_33cbedf0709949fd9416c8c864a86cf2` (Slack), content `''`: the only blank row of 511,962
(0 null, 0 whitespace-only). It is no question's expected doc.

**Non-functional Requirements**
- Shared NFRs. This is not text cleaning: every non-blank row is still embedded unchanged.
- A resumed run skips the 279,000 documents already in Qdrant (EVAL-3d1), so the fix costs
  nothing already paid for.

**Dependencies**
- APIs: `parquet_documents` in `pipeline/eval/documents.py`, unchanged signature
- Service Bus: N/A · Database: N/A · UI: N/A

## EVAL-3h  Precision in the report  ✅

**Status:** Done

**As a** RAG developer
**I want to** `score_retriever` to report `precision` next to hit rate, recall, MRR and NDCG
**So that** a clean-up story can show it sends the LLM less noise, not only that it finds more

**Acceptance Criteria (Gherkin)**
- Every `Scored` row carries `hit_rate`, `recall`, `precision`, `mrr`, `ndcg`
- Given a retriever returning 4 documents with 1 relevant, Then precision@10 is 0.25:
  LlamaIndex's `Precision` divides by the documents returned (at most k), not by k

**Example with real data**
377 of the 470 questions (80%) have exactly one relevant document, so their precision@10 can
never pass 0.1, even with the right document at rank 1. That is why EVAL-3c left precision out:
as a grade it looks like failure. As a comparison between two runs it is still the one number
that shows noise going down.

**Non-functional Requirements**
- Shared NFRs. Reuse: LlamaIndex's `precision` metric, no code of our own.
- The full baseline (EVAL-3e) was scored before this story; its precision is filled in by
  re-scoring the 470 questions (~25K Voyage tokens, ~$0.0015), no re-embedding.

**Dependencies**
- APIs: `METRICS` in `pipeline/eval/score.py`
- Service Bus: N/A · Database: N/A · UI: N/A

## EVAL-3e  The full run  ✅

**Status:** Done

`uv run python -m pipeline.eval.baseline --embed voyage-4`, recorded as **v0** in
`docs/eval/results.md` with its whole system (every stage, every choice, and the story behind it):
511,957 documents, 1,609,717 chunks, 470 questions, **recall@10 = 0.609**, the number every
clean-up story must beat.

Estimates that were wrong, kept so the next estimate starts from the real numbers:
- Chunks: ~1.3M estimated, 1,609,717 measured (3.1 per document).
- Time: ~2.5 h estimated with a local model; the local model ran at 22 chunks/s (~20 h), so
  EVAL-3f moved to Voyage, which ran at 80–160 chunks/s.
- Cost: ~425 Voyage tokens per chunk estimated; ~0.27 tokens per character held, so ~660M
  tokens in all.
- The run stopped once, at document 279,000, on the corpus's one empty row (EVAL-3g), and
  resumed without re-embedding what was done.

## EVAL-5  The evaluation report: three layers  (5a ✅, 5b ✅, 5c ✅)

Every number in the report is generated from the runs, never typed: one source of truth (the run
files in git), a summary generated from it (`results.md`), and an interactive page generated from
it (published as an artifact). Layer 1 is EVAL-5a, layer 2 EVAL-5b, layer 3 EVAL-5c.

## EVAL-5a  `write_run`  ✅

**Status:** Done

**As a** RAG developer
**I want to** each run's config, report rows and per-question scores written to a folder in git
**So that** every number in `results.md` traces to a committed file, and two runs can be
compared question by question

**Acceptance Criteria (Gherkin)**
- Given a config and 3 `Scored`, Then `metrics.json` holds the config and exactly the rows of
  `metrics_report` for them
- Given the same, Then `scored.jsonl` has one line per question and k, in order, each with
  `question_id`, `question_type`, `source_types`, `k` and `metrics`
- Given a re-run into the same folder, Then both files are replaced, not appended to

**Example with real data**
Before: the runs behind v0 and v1 (dense, BM25, relative and RRF fusion, exact and HNSW) lived
in `runs/`, which is gitignored, and kept only averages; RET-2 could not list the questions BM25
found and dense missed. After: `python -m pipeline.eval.baseline` writes
`docs/eval/runs/<date>-<collection>/metrics.json` and `scored.jsonl`; `events.jsonl` (a run log)
stays in `runs/`. The 12 existing runs' `metrics.json` are copied in (168 KB); their
per-question files come from re-scoring the exact runs after RET-3b (saved question vectors, $0).
A full run's `scored.jsonl` is 1,410 lines (470 questions × 3 k), ~0.3 MB.

**Non-functional Requirements**
- Shared NFRs. Reuse: `metrics_report` (EVAL-2b) makes the rows; `write_run` only writes them.

**Dependencies**
- APIs: `write_run(run_dir, config, scored)` in `pipeline/eval/report.py`; `baseline.RUNS`
- Service Bus: N/A · Database: N/A · UI: N/A

## EVAL-5b  `results_tables`  ✅

**Status:** Done

**As a** RAG developer
**I want to** the step-by-step tables in `results.md` generated from the run files
**So that** no number in the report is typed by hand, and a new run updates it with one command

**Acceptance Criteria (Gherkin)**
- Given 2 steps and runs with an overall and a slack group, Then one section per group (all
  sources first, then each source by question count), each with tables at k = 10, 5, 20
- Given a step, Then one row with its label, search mode and the five metrics to 3 decimals
- Given a column, Then its best value is bold, and so is every value that ties it as shown
- Given a step whose run folder is missing, Then `FileNotFoundError` naming the run
- Given `results.md` with the generated markers, Then only the text between them changes, and
  running twice gives the same file
- Given the real runs, Then the v1 row (hybrid RRF, exact) at k = 10 is hit 0.777, recall 0.722,
  precision 0.102 (bold: it ties relative score as shown), MRR 0.622, NDCG 0.619

**Example with real data**
`uv run python -m pipeline.eval.results_tables` writes 10 sections × 3 tables × 7 rows into
`docs/eval/results.md` under "v0 → v1, every step" (1,050 numbers). The first bolding rule
compared unrounded values, so precision@10 bolded relative score (0.1017…) but not RRF, which
also shows 0.102; bold now follows what the reader sees.

**Non-functional Requirements**
- Shared NFRs. Deterministic: same runs, same file. Hand-written text outside the markers is
  never touched.

**Dependencies**
- APIs: `Step`, `V1_STEPS`, `results_tables(steps, runs_dir)`, `replace_generated(text, generated)`,
  `python -m pipeline.eval.results_tables` in `pipeline/eval/results_tables.py`
- Service Bus: N/A · Database: reads `docs/eval/runs/*/metrics.json` · UI: N/A

## EVAL-5c  `html_report`  ✅

**Status:** Done

**As a** RAG developer
**I want to** one self-contained HTML page, generated from the runs, that shows every v1 step
side by side for all questions and for each source
**So that** I can see where each retrieval step wins or loses without typing a number, and share
the page as an artifact

**Acceptance Criteria (Gherkin)**
- Given two runs with groups overall, `type:basic`, `source:jira` (3 questions) and
  `source:slack` (1), Then the buttons are All, jira, slack (sources by question count, no types)
- Given the same, Then for overall and each source the page embeds, at k = 10, 5 and 20 in that
  order, one row per step with its label, search and values to 3 decimals
- Given the same, Then each row names the metric columns where its value is the best, and the
  page draws those cells with the `best` class
- Given a step whose run folder has no `metrics.json`, Then `FileNotFoundError` names the run
- Given the page, Then it loads no external script or stylesheet and has a dark mode

**Example with real data**
Before: the v1 step table showed overall recall@10 only (dense 0.626, BM25 0.650, relative 0.727,
RRF 0.722, all exact), so nothing showed where RRF loses. After: `python -m pipeline.eval.html_report`
writes `docs/eval/report.html` (39 KB) from the 7 runs in `V1_STEPS`: buttons All (470),
confluence (114), jira (100), slack (79), github (60), google_drive (60), linear (58), gmail (55),
hubspot (34), fireflies (25). On All, k = 10, RRF (v1) exact reads hit rate 0.777, recall 0.722,
precision 0.102, MRR 0.622, NDCG 0.619; relative exact is best in every column (recall 0.727).
On hubspot, BM25 alone is best in every column (recall 0.574) and RRF (v1) exact trails it at
0.515; on jira RRF (v1) exact reaches 0.782.

**Non-functional Requirements**
- Shared NFRs. Reuse: reads the `metrics.json` that `write_run` (EVAL-5a) writes; no number is
  recomputed or typed. No external scripts, CSS inline, data embedded as JSON; light and dark mode
  via CSS variables; tables scroll inside their own container at phone width.

**Dependencies**
- APIs: `html_report(steps, runs_dir, title)`, `V1_STEPS`, `main()` in `pipeline/eval/html_report.py`
- Service Bus: N/A · Database: N/A · UI: `docs/eval/report.html`

**Update (RET-6):** the page gained a version strip (`VERSIONS`: v0 → v1 → v2 with recall@10,
MRR@10 and each gain), the three reranker steps, and the artifact page contract (theme tokens
guarded for the viewer's light/dark/system setting, IBM Plex via Google Fonts, a one-column grid
that keeps wide tables inside their own scroll box). Title: "EnterpriseRAG Retrieval Scoreboard".

## EVAL-3i  `document_text`: the title merged into the text  ✅

**Status:** Done (BM25 measured; dense not re-embedded)

**As a** RAG developer
**I want to** each document's title to open its text, so both searches can match it
**So that** a question that names a record ("NorthPoint Signalworks") finds it

**Why:** EVAL-3a kept `title` out of the embedded text for every document, because 497 titles
(493 Slack) hold a whole body and overflowed SentenceSplitter's 512-token chunk as metadata. That
hid the name of all the others: qst_0063 asks for "NorthPoint Signalworks", which appears only in
its HubSpot record's title, so neither dense nor BM25 search could match it. At top 100, 4 misses
had this cause (2 HubSpot, 2 Slack).

**Acceptance Criteria (Gherkin)**
- Given a title and a body, Then the text is the stripped title, a blank line, then the body
- Given a body that already starts with the title, Then it is kept as it is (1,697 rows)
- Given a blank or missing title, Then the body alone (15 Slack rows)
- Given `parquet_documents(..., with_title=True)`, Then the text is `document_text` and the title
  stays metadata; without it the baseline is unchanged
- Given the real corpus, Then NorthPoint Signalworks' text starts with its name

**Edge cases (all 511,962 rows):** median title 12 chars, p99 107, longest 10,692; 1,062 titles
over 200 chars (1,057 Slack), prepended like any title since as text they cannot overflow.

**Measured: BM25 only, $0.** A new collection `bm25_titles`: the corpus with titles, the
baseline's SentenceSplitter(512, 50), BM25 (a 1-number placeholder dense vector, never searched),
1,619,566 chunks in 20 min.

| exact, top 50 | hit@10 | recall@10 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|
| BM25 (RET-2) | 0.709 | 0.650 | 0.094 | 0.560 | 0.554 |
| **BM25 with titles** | **0.740** | **0.688** | **0.099** | **0.590** | **0.586** |

Question by question: recall@10 better for 27, worse for 5, +0.038 [95% bootstrap +0.021,
+0.056]; MRR +0.029 [+0.014, +0.047]. qst_0063 and qst_0120 go from 0 to 1. By source: HubSpot
0.574 → **0.706**, Confluence 0.606 → 0.670, Google Drive 0.603 → 0.666, Gmail 0.672 → 0.695, the
rest within ±0.02.

**Not a fair hybrid yet.** Fusing v1's dense (chunks without titles) with this BM25 (chunks with
titles) keeps recall@10 at 0.722 but drops MRR@10 from 0.622 to 0.498: the two lists no longer
share chunks, so RRF never sees the same chunk found by both and loses its agreement boost. A
fair hybrid needs the dense vectors of the same chunks, i.e. a Voyage re-embed of the corpus with
titles (cost to be confirmed before running).

**Dependencies**
- APIs: `document_text(title, content)`, `parquet_documents(..., with_title=False)` in `pipeline/eval/documents.py`
- Database: Qdrant `bm25_titles`; runs in `docs/eval/runs/*-bm25-titles`, `*-hybrid-rrf-titles-exact`

**Update (EVAL-3j): v3 recorded on BM25 with titles.** The chain re-run with this BM25 in place
of the untitled one: v1's dense + BM25 with titles, RRF over 200-deep lists (exact), the top 100
reranked by rerank-3-lite (23,060,737 tokens, 288 s, free pool). Pool recall at top 100 0.878 →
0.888; after reranking recall@10 **0.845** against 0.832 without titles (better on 12 questions,
worse on 2, +0.013 [95% CI +0.002, +0.025]), MRR@10 0.818, hit@10 0.891. HubSpot 0.765 → **0.853**,
Fireflies 0.665 → 0.725, completeness 0.570 → 0.620. This is **v3** (+0.045 over v2's 0.800).
`TITLED_STEPS` is now the report's step list (`results.md`, `report.html`), the untitled runs
stay in `docs/eval/runs`; the highlighted row follows the last version. The dense vectors still
lack titles: re-embedding them is the next paid step.

## EVAL-3k  voyage-4-lite dense vectors with titles  ✅

**Status:** Done (measured; not adopted, v3 stays)

**Why:** in EVAL-3j the hybrid fused dense chunks without titles with BM25 chunks with titles, so
RRF never saw the same chunk twice (MRR@10 0.498). Re-embedding the corpus with titles gives both
searches the same chunks. `voyage-4-lite` ($0.02 per 1M tokens against $0.06, estimated 583M
tokens) shares voyage-4's embedding space, so the 470 saved voyage-4 question vectors search it
directly (the same text embedded by both: cosine 0.969).

**What changed:** `EMBEDDERS` gains `voyage-4-lite` (1,024 dimensions);
`ingest_corpus(..., with_title=True)`. One collection, `titles__voyage_4_lite__bm25`: dense
(voyage-4-lite) and BM25 of the same titled chunks. 1,619,571 chunks in 3 h 32 min overnight
(bm25_titles holds 1,619,566; 2 documents differ by 5 chunks, re-ingested with the same result).

| exact | hit@10 | recall@10 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|
| dense: voyage-4, no titles (v0 exact) | 0.687 | **0.626** | 0.088 | **0.508** | **0.508** |
| dense: voyage-4-lite, titles | 0.666 | 0.606 | 0.086 | 0.483 | 0.487 |
| hybrid RRF: v1 (no titles) | 0.777 | 0.722 | 0.102 | **0.622** | **0.619** |
| hybrid RRF: voyage-4 dense + BM25 with titles (EVAL-3j) | 0.772 | 0.722 | 0.102 | 0.498 | 0.530 |
| hybrid RRF: voyage-4-lite + BM25, both with titles | **0.785** | **0.732** | **0.104** | 0.612 | 0.615 |
| **v3**: voyage-4 dense + BM25 with titles, top 100 reranked | **0.891** | **0.845** | **0.118** | **0.818** | **0.799** |
| voyage-4-lite + BM25 with titles, top 100 reranked | 0.879 | 0.834 | 0.116 | 0.809 | 0.790 |

Pool recall at top 100: 0.888 (v3) against 0.877 (lite). After reranking, against v3: recall@10
−0.011 (better on 3 questions, worse on 11; 95% CI [−0.024, +0.001]), MRR −0.009. By source it
loses most on Linear (0.887 → 0.852) and Google Drive (0.807 → 0.786); HubSpot stays 0.853.

**What it says:** titles did not make up for the smaller model. voyage-4-lite with titles is
0.020 below voyage-4 without them on dense alone, and the shared chunks restore RRF's agreement
(hybrid MRR 0.498 → 0.612) without lifting the reranked result. v3 stays; the next dense step,
if any, is voyage-4 with titles (~$35 at $0.06 per 1M tokens).

**Dependencies**
- APIs: `EMBEDDERS["voyage-4-lite"]`, `ingest_corpus(..., with_title=)`
- Database: Qdrant `titles__voyage_4_lite__bm25`; runs in `docs/eval/runs/2026-09-28-titles__voyage_4_lite__bm25-*`

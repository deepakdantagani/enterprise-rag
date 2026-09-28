# Retrieval stories

How candidate chunks get found, beyond v0's dense-only search. Rules and template:
[stories.md](../stories.md). Scores go in [results.md](../eval/results.md), one row per version.

Why this comes next: v0 (EVAL-3e) searches by meaning only, one Voyage vector per chunk, and
scores recall@10 = 0.609. One vector has to compress a whole chunk, so exact names, ids and
numbers blur: HubSpot (short CRM fields) scores 0.353. Keyword search (BM25) matches exact
words, dense search matches meaning; hybrid search runs both and fuses the two lists. v1 is
v0 plus hybrid search, with the same chunks and no cleaning, so any gain is the search alone.
Per-source clean-up comes after, measured against v1, one change per run.

Retrieval glossary:

- **Dense vector**: v0's 1,024-number Voyage `voyage-4` embedding. Every number is used; none
  means anything alone.
- **Sparse vector**: one entry per distinct word in the chunk: `indices` are hashed, stemmed
  words, `values` their BM25 term-frequency weight. Every other word is absent.
- **BM25**: rarity of the word (IDF) × its capped, length-adjusted frequency in the chunk.
  `Qdrant/bm25` in FastEmbed is no neural model: a stopword list, a Snowball stemmer and the
  formula (k = 1.2, b = 0.75, avg_len = 256). Qdrant applies IDF at search time.
- **Hybrid collection**: one Qdrant point per chunk holding two named vectors, `text-dense`
  and `text-sparse-new` (LlamaIndex's default names).
- **Fusion**: merging the dense and sparse result lists into one. LlamaIndex defaults to
  `relative_score_fusion` (on scores); RRF (on ranks) is a deliberate choice (RET-3).

| Story | Status |
|---|---|
| RET-1  `copy_to_hybrid`: v0 chunks into a hybrid collection, dense unchanged, plus BM25 | ✅ |
| RET-2  `sparse_retriever`: BM25 alone scored on the 470 questions | ✅ |
| RET-3a  `saved_query_embeddings`: re-score without paying Voyage again | ✅ |
| RET-3b  `dense_retriever`, `hybrid_retriever`: exact search; RRF chosen for v1 | ✅ |
| RET-4  v1 recorded: hybrid RRF, exact, recall@10 0.722 | ✅ |
| RET-5  `rerank_saved`, `replay_retriever`: v1's top 50 reranked by three Voyage cross-encoders | ✅ |
| RET-6  v2 recorded: v1 + rerank-3-lite, recall@10 0.800; the scoreboard page published | ✅ |
| RET-7  `multi_query_retriever`: the question + 3 local-LLM queries, fused by RRF (measured: worse than v1) | ✅ |
| RET-7b  the query prompt: keep the question's details (recall@50 0.838 → 0.848; reranked 0.807 vs v2 0.800, within noise: v2 stays) | ✅ |

---

## RET-1  `copy_to_hybrid`  ✅

**Status:** Done

**As a** RAG developer
**I want to** every chunk of `baseline__voyage_4` copied into a hybrid collection with its
Voyage vector unchanged and a BM25 sparse vector added
**So that** RET-2 can score keyword search and RET-3 can fuse both, without re-embedding

**Acceptance Criteria (Gherkin)**
- Given 3 chunks in a v0-style collection and `page_size = 2`, Then 3 are copied, each with the
  same id, the same payload and `text-dense` equal to the v0 vector
- Given any copied chunk, Then it has a non-empty `text-sparse-new` of its own words
- Given the hybrid collection, Then its sparse vector config has Qdrant's IDF modifier
- Given a re-run, Then 0 are copied and the collection still holds 3 points
- Given the real runbook chunk `0e9ae45d…` from v0, Then its BM25 vector has 157 words and the
  top weight is 1.986 (`canari`, 11 times)

**Example with real data**
The first chunk of "Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod)" (Confluence,
`dsid_e54ef48b…`, 2,257 chars). Before, in v0: one unnamed vector
`[0.0494, -0.0224, 0.0307, …]` and 7 payload fields. After: `text-dense` holds the same 1,024
numbers, the same 7 payload fields, and `text-sparse-new` has 157 entries: `canari` 1.986
(11 times), `perf` 1.945 (9), `must` 1.838 (6) … `approv` 1.008 (1). Check by hand with 251
words after stopwords: `1 × 2.2 / (1 + 1.2 × (0.25 + 0.75 × 251/256)) = 1.008`.

**Measured on 2,000 chunks (first in scroll order: 810 Slack, 717 Gmail, … 19 Jira)**
- 1,072 chunks/s (0.5 s reading v0, 1.4 s BM25 + writing), so ~25 min for 1,609,717.
- BM25 entries per chunk: mean 131, median 138, max 207, none empty (~1.7 GB for all).
- Words per chunk after stopwords and stemming: mean 195, median 215, vs the model's 256.
- Qdrant used 8.3 GB of Docker's 15.8 GB with v0 alone; a second copy of the dense vectors
  needs about as much again.

**Decisions**
- Docker memory raised to 24 GB (the Mac has 64 GB), so v0 and the hybrid collection both stay
  in RAM and v0 remains for re-scoring. Rejected: dense vectors on disk (slower scoring) and
  deleting v0 (irreversible without ~$38 of re-embedding).
- `avg_len` stays at the model's 256: LlamaIndex's encoder can't pass it, and the effect is
  small. Tuning `avg_len`, `k` and `b` is its own story after v1, one change at a time.
- A new collection, `hybrid__voyage_4__bm25`: LlamaIndex's hybrid store expects a dense vector
  named `text-dense` (v0's is unnamed), and v0 stays untouched as the baseline.
- `Qdrant/bm25` named explicitly: LlamaIndex's default sparse model is a SPLADE-style neural
  one. SPLADE stays a possible later story if v1 shows BM25 missing paraphrases.

**Non-functional Requirements**
- Shared NFRs. Reuse: LlamaIndex's `QdrantVectorStore(enable_hybrid=True)` creates the
  collection and computes BM25; `metadata_dict_to_node` rebuilds each node from its payload.
  Our code is only the copy loop.
- $0: the stored vector is set as the node's embedding, so the store never calls Voyage.
- Resumable: each page asks the target which ids it already holds.
- New dependency: `fastembed==0.8.1` (and its `onnxruntime`, unused by BM25).

**Dependencies**
- APIs: `hybrid_store(client, collection_name, aclient=None)`, `node_from_point(point)`,
  `copy_to_hybrid(client, source, store, page_size=1000) -> int` in `pipeline/eval/hybrid.py`
- Service Bus: N/A · Database: new Qdrant collection `hybrid__voyage_4__bm25` · UI: N/A

## RET-2  `sparse_retriever`: BM25 alone  ✅

**Status:** Done

**As a** RAG developer
**I want to** keyword search scored on its own, with v0's metrics, on the RET-1 collection
**So that** I know what BM25 finds and misses before fusing it with dense search (RET-3)

**Acceptance Criteria (Gherkin)**
- Given 3 chunks whose dense vectors would rank "The Berlin office moved." first, When asked
  "Who approved the Q3 budget?", Then BM25 returns "Priya approved the Q3 budget." first
- Given "Roll back perf-canary", Then only the chunk sharing those words is returned
- Given `top_k = 2`, Then at most 2 chunks come back
- Given the real collection and qst_0017 ("… tiered uptime SLA counteroffer for the maritime
  logistics SaaS customer …"), Then the first chunk is from `dsid_03af1e44970d4d6db6e85bc2c5fce8de`

**Example with real data**
Four HubSpot questions, BM25 only: qst_0017 and qst_0042 find their record at rank 1 (rare
words like "counteroffer", "maritime", "Hacker News"); qst_0015 misses (its words — latency,
concurrent, streaming, chat — are common); qst_0063 misses because "NorthPoint" matches a
different company's Fireflies meeting ("Strategic Health & Burn Council - Northpoint Health Q1").

**Result: all 470 questions, 12 s, $0** (row in [results.md](../eval/results.md))

| | hit@10 | recall@5 | recall@10 | recall@20 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|---|
| dense (v0) | 0.668 | 0.531 | 0.609 | 0.673 | 0.085 | 0.493 | 0.494 |
| BM25 alone | 0.709 | 0.587 | **0.650** | 0.721 | 0.094 | 0.560 | 0.554 |

Recall@10 by source, dense → BM25: Fireflies 0.265 → **0.620**, HubSpot 0.353 → **0.574**,
Gmail 0.536 → 0.672, Linear 0.611 → 0.706, Confluence 0.567 → 0.606, Google Drive 0.575 → 0.603,
Jira 0.719 → 0.724, Slack 0.632 → **0.583**, GitHub 0.669 → **0.617**.
By type: intra_document_reasoning 0.700 → 1.000, conflicting_info 0.500 → 0.750, miscellaneous
0.700 → 0.900, completeness 0.402 → 0.496, project_related 0.558 → 0.594, basic 0.697 → 0.703,
semantic 0.440 → **0.416**, constrained 0.900 → **0.800**.

What it says: keyword search alone beats v0's dense search, most on the sources full of exact
names (transcripts, CRM records, email). It loses where meaning matters more than words
(semantic questions, chatty Slack, code). The two win on different sources and question types,
which is the case for fusing them in RET-3 (per-question overlap is not measured yet).

**Decisions**
- Sparse only: the dense-vs-BM25 per-question table (complementarity) is left out; it needs
  per-question results saved for both runs, a story of its own if RET-3 needs it.
- `MockEmbedding` as the retriever's embed model: LlamaIndex's retriever embeds every question
  even in sparse mode (`is_embedding_query`) and never reads that vector, so a mock costs $0
  where Voyage would cost ~$0.0015. Still the library retriever, no query code of our own.
- 50 chunks, as in v0, so both are compared at the same depth.

**Non-functional Requirements**
- Shared NFRs. Reuse: `VectorStoreIndex.as_retriever(vector_store_query_mode="sparse")`,
  `score_retriever` (EVAL-3c) and `metrics_report` (EVAL-2b), unchanged.
- $0 and deterministic: BM25 is local, the mock embedding is fixed.

**Dependencies**
- APIs: `sparse_retriever(store, top_k=50) -> BaseRetriever` in `pipeline/eval/hybrid.py`
- Service Bus: N/A · Database: reads `hybrid__voyage_4__bm25` · UI: N/A

## RET-3a  `saved_query_embeddings`  ✅

**Status:** Done

**As a** RAG developer
**I want to** the scorer to reuse the 470 question vectors already embedded by Voyage
**So that** every re-score (exact search, fusion choices, per-source clean-up) costs $0 and
runs in seconds

**Acceptance Criteria (Gherkin)**
- Given a saved question, Then its saved vector comes back and the fallback is never called
- Given the async path the scorer uses (`aget_query_embedding`), Then the same saved vector
- Given a question not in the file, Then the fallback (Voyage) embeds it
- Given a question not in the file and no fallback, Then `KeyError` naming the question
- Given the real file, Then 470 vectors of 1,024 numbers

**Example with real data**
The RET-3 measure step scored dense, relative-score and RRF retrieval on the hybrid collection.
The scorer retrieves each question once per k (5, 10, 20), and LlamaIndex's retriever embeds
the question each time: 1,410 Voyage calls per run, ~10 minutes, ~$0.0045; the three runs cost
~$0.013, three times the estimate. The 470 questions were then embedded once (95 s,
`input_type` "query") into `data/_index/question_embeddings/voyage-4.jsonl` (10.8 MB). Dense
re-scored from that file, with no fallback so any Voyage call would fail: recall@10 0.599 and
MRR@10 0.486, identical to the paid run, in 12 s, 0 Voyage calls.

**What the saved vectors found (the reason for RET-3b)**
With exact (brute-force) search, v0 and the hybrid collection both score recall@10 **0.625**,
and 462 of 470 questions get identical top-50 chunks: the RET-1 copy is faithful. Approximate
(HNSW) search scored 0.608 on v0 and 0.598 on the hybrid collection, and matched the exact
top 50 for only 254 and 212 of 470 questions. So every dense number so far is understated by
index settings, and that noise (0.01–0.03) is as big as the relative-score vs RRF gap (0.010).
Exact search costs 53 ms per question against 7 ms: ~75 s per scoring run.

**Decisions**
- Keyed by question text, not id: the retriever only sees the text.
- No write-back of new questions: the fallback embeds them, the file stays the 470 of
  `questions.jsonl`. A new question set gets its own file.
- Chunk embedding is refused (`NotImplementedError`): this model is for questions only.

**Non-functional Requirements**
- Shared NFRs. Reuse: LlamaIndex's `BaseEmbedding` is the extension point for embed models;
  there is no built-in query-embedding cache (`IngestionCache` covers documents).
- Known issue: a script that loads FastEmbed can print `libc++abi … recursive_mutex lock failed`
  at interpreter exit, after its work is done; results are unaffected.

**Dependencies**
- APIs: `SavedQueryEmbedding(saved, fallback=None)`, `saved_query_embeddings(path, fallback=None)`
  in `pipeline/eval/embedders.py`
- Service Bus: N/A · Database: reads `data/_index/question_embeddings/voyage-4.jsonl` · UI: N/A

## RET-3b  `dense_retriever` and `hybrid_retriever`: exact search, RRF chosen  ✅

**Status:** Done

**As a** RAG developer
**I want to** dense and hybrid retrievers that search exactly, with the fusion as a choice
**So that** fusion options are compared on numbers the HNSW index cannot blur, and v1 is chosen
on a measurement

**Acceptance Criteria (Gherkin)**
- Given a question embedded as one chunk's vector, Then `dense_retriever` returns that chunk
  first, and passes `search_params {"exact": true}` to Qdrant
- Given fusion "relative", Then the first two chunks are dense's first and BM25's first
- Given fusion "rrf", Then the same two, from `QueryFusionRetriever` in `reciprocal_rerank` mode
  with `num_queries = 1` (no LLM rewrites the question)
- Given an unknown fusion, Then `ValueError` naming "relative, rrf"

**Result: all 470 questions, exact search, saved question vectors: 0 Voyage calls, ~5 min, $0**

| exact search | recall@5 | recall@10 | recall@20 | mrr@10 | ndcg@10 | hit@10 |
|---|---|---|---|---|---|---|
| v0 dense (`baseline__voyage_4`) | 0.548 | 0.626 | 0.698 | 0.508 | 0.508 | 0.687 |
| dense (hybrid collection) | 0.548 | 0.626 | 0.698 | 0.508 | 0.508 | 0.687 |
| BM25 alone | 0.587 | 0.650 | 0.721 | 0.560 | 0.554 | 0.709 |
| hybrid, relative score (alpha 0.5) | 0.664 | 0.727 | 0.784 | 0.638 | 0.630 | 0.781 |
| **hybrid, RRF (k 60)** | **0.676** | **0.722** | **0.791** | 0.622 | 0.619 | 0.777 |

Recall@10 by source (dense / BM25 / relative / RRF): Confluence 0.572 / 0.606 / 0.667 / 0.680,
Fireflies 0.345 / 0.620 / 0.580 / 0.540, GitHub 0.673 / 0.617 / 0.716 / 0.717, Gmail
0.554 / 0.672 / 0.694 / 0.696, Google Drive 0.585 / 0.603 / 0.691 / 0.666, HubSpot
0.353 / 0.574 / 0.544 / 0.515, Jira 0.738 / 0.724 / 0.787 / 0.782, Linear 0.593 / 0.706 / 0.754 /
0.756, Slack 0.684 / 0.583 / 0.731 / 0.721.

What it says:
- Exact search makes the two collections identical (0.626): the copy is faithful, and v0's true
  dense score is 0.626, not the 0.609 the approximate index gave.
- Hybrid adds ~0.10 recall@10 over dense, with either fusion.
- Relative score and RRF are a tie: 0.005 apart at k = 10 (2–3 questions), RRF ahead at k = 5
  and k = 20, relative ahead on MRR and NDCG.
- Fireflies (10,173 meeting summaries, median 11,080 chars, ~7 chunks each) and HubSpot (15,017
  account notes, median 3,025 chars) still score higher with BM25 alone: many documents share
  topics (POCs, latency, pricing), and the customer name that tells them apart is what BM25
  matches and a dense vector blurs.

**Decisions**
- **RRF for v1.** The two are tied on our questions, and RRF is the default of Azure AI Search,
  Elasticsearch's `rrf` retriever and Qdrant's hybrid queries: no weights to tune. It is not
  LlamaIndex's default (its hybrid mode uses relative score), so v1 uses `QueryFusionRetriever`.
- Relative score with a tuned `alpha` stays a future story: weighted score fusion is where
  engines go once an evaluation set exists (OpenSearch reports RRF ~3.9% lower NDCG@10 on BEIR).
- Exact search for every evaluation (53 ms a question vs 7 ms); `hnsw_ef` tuning is a later
  latency story, measured against the exact number.
- `use_async=False` on `QueryFusionRetriever`: only a plain `retrieve()` call reads it; the
  scorer's `aretrieve` always runs both searches concurrently.

**Non-functional Requirements**
- Shared NFRs. Reuse: `as_retriever(vector_store_kwargs={"search_params": {"exact": True}})`,
  LlamaIndex's hybrid mode and `QueryFusionRetriever`; no fusion code of our own.
- $0: question vectors from RET-3a.

**Dependencies**
- APIs: `dense_retriever(store, embed_model, top_k=50)`,
  `hybrid_retriever(store, embed_model, fusion, top_k=50)` in `pipeline/eval/hybrid.py`
- Service Bus: N/A · Database: reads `hybrid__voyage_4__bm25` and `baseline__voyage_4` · UI: N/A

## RET-4  v1 recorded  ✅

**Status:** Done

v1 is v0's chunks and Voyage vectors plus BM25 (RET-1), searched exactly and fused by RRF
(RET-3b): `hybrid_retriever(store, embed_model, "rrf")` on `hybrid__voyage_4__bm25`, top 50
chunks. Scored on the 470 questions (run `docs/eval/runs/2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf-exact`):

| | hit@10 | recall@5 | recall@10 | recall@20 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|---|
| v0, exact | 0.687 | 0.548 | 0.626 | 0.698 | 0.088 | 0.508 | 0.508 |
| **v1** | 0.777 | 0.676 | **0.722** | 0.791 | 0.102 | 0.622 | 0.619 |

Recorded as the headline rows of [results.md](../eval/results.md), with every step (dense, BM25,
relative, RRF; exact and HNSW; all sources and each source) generated below them (EVAL-5b) and in
`docs/eval/report.html` (EVAL-5c). v0's own row stays at 0.609: that is what the HNSW index
returned then; the exact row (0.626) is the fair comparison.

Where v1 is still weakest: HubSpot (0.515) and Fireflies (0.540), where BM25 alone scores higher
(0.574, 0.620); and `completeness` (0.493) and `semantic` (0.496) questions.

## RET-5  Reranking v1's top 50: `rerank_saved` and `replay_retriever`  ✅

**Status:** Done

**As a** RAG developer
**I want to** v1's 50 candidates re-sorted by a cross-encoder reranker, each question reranked
once per model and the order saved
**So that** rerankers are compared on the same candidates, and every re-score is $0

**Acceptance Criteria (Gherkin)**
- Given 2 saved questions and a reranker, Then it is called once per question and each order,
  its scores and the tokens are saved; the call returns the tokens used
- Given a re-run, Then no question is reranked again and 0 tokens are used
- Given no rerank file, Then the replay returns the candidates as retrieved (v1's own order)
- Given a rerank file, Then the replay returns them in the reranked order, best score first
- Given a question with no saved candidates, Then `KeyError` naming it
- Given Voyage's answer (results with index and relevance_score, total_tokens), Then
  `voyage_rerank` returns order, scores and tokens
- Given the real files, Then rerank-3-lite puts qst_0001's third v1 candidate first

**Example with real data**
v1 finds a relevant document in its top 20 for recall 0.791 but in its top 10 for 0.722. The
top 50 of all 470 questions was saved once (`data/_index/rerank/v1_candidates.jsonl`, 48.6 MB, 28 s,
$0); replaying it without a reranker reproduces v1 exactly (recall@5/10/20 0.676/0.722/0.791,
MRR@10 0.622). Each question is one Voyage request: query tokens × 50 + the 50 chunks, 23,366
tokens for qst_0001; 11,524,826 tokens per model for the 470, inside the 200M free tokens of each.

| v1 top 50, reranked by | time | recall@5 | recall@10 | recall@20 | hit@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|---|
| none (v1) | | 0.676 | 0.722 | 0.791 | 0.777 | 0.622 | 0.619 |
| `rerank-2.5` (generally available) | 583 s | 0.762 | 0.791 | 0.811 | 0.847 | 0.769 | 0.742 |
| `rerank-3-lite` (preview) | 182 s | 0.777 | **0.800** | 0.820 | 0.851 | 0.785 | **0.762** |
| `rerank-3` (preview) | 633 s | **0.778** | 0.798 | 0.817 | **0.853** | **0.786** | 0.760 |

Recall@10 by source, v1 → rerank-3-lite: HubSpot 0.515 → **0.765**, Fireflies 0.540 → 0.645
(0.665 with rerank-3 and rerank-2.5), Gmail 0.696 → 0.791, Google Drive 0.666 → 0.748, Linear
0.756 → 0.826, Confluence 0.680 → 0.717, Slack 0.721 → 0.777, GitHub 0.717 → 0.781, Jira 0.782 →
0.823. By type: semantic 0.496 → **0.688**, basic 0.800 → 0.851, completeness 0.493 → 0.576.

What it says: a reranker adds ~+0.08 recall@10 and ~+0.16 MRR@10 over v1, the biggest step since
hybrid search. It fixes exactly where fusion hurt: HubSpot and Fireflies, where BM25 alone had
beaten v1, now beat BM25 alone (0.765 vs 0.574, 0.645 vs 0.620). The three models are within
0.009 of each other; recall@20 moves little (0.791 → 0.820) because reranking only re-sorts the
50 v1 found.

**Decisions**
- Rerank once per question and replay: the scorer asks each question at k = 5, 10 and 20, and a
  live reranker would triple the tokens; the replay also makes every re-score reproducible.
- Measured with Voyage's client (`voyageai.Client.rerank`), the library LlamaIndex's
  `VoyageAIRerank` postprocessor wraps; a serving pipeline would use the postprocessor.
- rerank-3-lite chosen for v2 (RET-6): tied with rerank-3 (0.800 vs 0.798), 3.5× faster and 2.5×
  cheaper; rerank-2.5, the generally available one, is 0.009 behind.

**Non-functional Requirements**
- Shared NFRs. Reuse: `score_retriever`, `metrics_report` and `write_run` unchanged; the replay is
  a LlamaIndex `BaseRetriever`.
- Resumable, and $0 after the first pass per model.

**Dependencies**
- APIs: `rerank_saved(candidates_path, out_path, rerank)`, `voyage_rerank(client, model)`,
  `ReplayRetriever`, `replay_retriever(candidates_path, rerank_path=None)` in
  `pipeline/eval/rerank.py`; `RERANK_STEPS`, `REPORT_STEPS` in `pipeline/eval/results_tables.py`
- Service Bus: N/A · Database: `data/_index/rerank/` (gitignored); runs in `docs/eval/runs/*-rrf-rerank-*` · UI: `docs/eval/report.html`

## RET-6  v2 recorded: v1 + `rerank-3-lite`  ✅

**Status:** Done

v2 is v1 (hybrid RRF, exact, top 50 chunks) with the 50 re-sorted by Voyage's `rerank-3-lite`
cross-encoder (preview on 2026-09-27). Chosen over `rerank-3` (tied: 0.798) for being 3.5× faster
(182 s vs 633 s for 470 questions) and 2.5× cheaper ($0.02 vs $0.05 per 1M tokens).

| version | change | recall@10 | gain | mrr@10 |
|---|---|---|---|---|
| v0 | dense search, voyage-4 vectors (exact) | 0.626 | | 0.508 |
| v1 | + BM25, fused by RRF | 0.722 | +0.096 | 0.622 |
| **v2** | + rerank-3-lite on the top 50 | **0.800** | +0.078 | 0.785 |

The report now names versions: `VERSIONS` in `pipeline/eval/html_report.py` puts v0 → v1 → v2 at
the top of `docs/eval/report.html` ("EnterpriseRAG Retrieval Scoreboard"), with recall@10, MRR@10
and each version's gain, above every step by source. The page follows the artifact page contract
(light and dark themes that follow the viewer and the toggle, IBM Plex from Google Fonts as its
only outside resource, tables that scroll inside their own box at phone width) and is published as
a private artifact. The v2 row in the step tables is labelled "5. v1 + rerank-3-lite (v2)".

Risk: `rerank-3-lite` is a preview model and can change; the saved reranking
(`data/_index/rerank/rerank-3-lite.jsonl`) keeps these numbers reproducible, and `rerank-2.5`
(0.791) is the generally available fallback.

**Update:** the reports (`results.md` tables and `report.html`) show only the chosen reranker,
"5. v1 + rerank-3-lite (v2)". The rerank-2.5 and rerank-3 runs stay in `docs/eval/runs` and in
the RET-5 table above as the evidence for the choice.

## RET-7  `multi_query_retriever`: the question + 3 LLM-written queries  ✅

**Status:** Done (measured; not adopted)

**As a** RAG developer
**I want to** v1's hybrid search run for the question and for 3 queries an LLM writes from it,
all result lists fused by RRF
**So that** relevant documents v1 never retrieves reach the top 50 the reranker sees

**Why:** v2 finds 526 of the 741 relevant documents in its top 10; 54 more are in v1's top 50 and
**161 are not in it at all**, so no reranker can lift them. qst_0436 ("Across Redwood's Go,
Python, and TypeScript SDKs, which SDK has the most customer-reported auth-related bug
reports …") needs 10 documents; v1 retrieves 1.

**Acceptance Criteria (Gherkin)**
- Given 2 questions and a planner LLM, Then each is planned once and its prompt and answer saved;
  a re-run plans nothing; the saved answers replay without the LLM; an unsaved prompt → `KeyError`
- Given the retriever, Then it is LlamaIndex's `QueryFusionRetriever` with its default prompt,
  `num_queries=4` (the question + 3) and RRF, and `generated_queries` returns the 3 parsed queries
- Given a chunk only the generated queries find, Then it is returned
- Given the real planner file, Then all 470 questions have a saved plan

**Example with real data**
Nothing is custom but the save-and-replay: `QueryFusionRetriever` (the class v1 already runs with
`num_queries=1`) with its default prompt ("You are a helpful assistant that generates multiple
search queries based on a single input query …"). The planner is `gemma4:26b` on Ollama, local:
470 questions in 297 s, $0. (`qwen3:30b` was tried first: it ignored `thinking=False` and wrote
its reasoning into the answer, 12–31 s a question.) The 1,410 new queries were embedded once by
voyage-4 (16,899 tokens, $0.001) into `data/_index/question_embeddings/voyage-4-generated.jsonl`;
the top 50 of each question was saved (`data/_index/rerank/multi_query_candidates.jsonl`).

qst_0436's 3 queries: "Redwood SDK auth bug reports by language Go Python TypeScript",
"Redwood SDK authentication support ticket IDs for bug reports", "Comparison of auth-related bug
reports in Redwood Go Python and TypeScript SDKs": rephrasings, not one query per SDK. It still
finds 1 of its 10 documents.

| before reranking (exact) | recall@50 | recall@20 | recall@10 | hit@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|
| v1: the question alone | **0.838** | **0.791** | **0.722** | **0.777** | **0.622** | **0.619** |
| + 3 generated queries | 0.818 | 0.746 | 0.701 | 0.755 | 0.577 | 0.579 |

Against v1's top 50 it gains 21 relevant documents and loses 42. Recall@50 drops for every
large question type: completeness 0.651 → 0.603, project_related 0.801 → 0.768, semantic 0.696 →
0.648, basic 0.897 → 0.891.

What it says: RRF gives the question 2 of the 8 result lists; the 3 paraphrases get 6, and when
they drift ("best practices for defining design tokens …" for qst_0003) their documents push the
question's own out of the top 50. Default multi-query is a net loss here, so the reranking step
was not run (it can only re-sort a top 50 that now holds fewer relevant documents). v2 stays.

**Decisions**
- LlamaIndex's `QueryFusionRetriever` and its default prompt, unchanged: one change at a time,
  so the result is attributable to multi-query itself.
- Plan once and replay (`SavedCompletions`, a LlamaIndex `CustomLLM`): the scorer asks each
  question at k = 5, 10 and 20, and a replay makes every re-score identical and $0.

**Follow-ups (not started)**
- Keep v1's top 50 and add only what the generated queries find beyond it, then rerank: the
  reranker decides, so the 21 gains can count without the 42 losses.
- A decomposition prompt (one query per part or item) for completeness questions like qst_0436.

**Dependencies**
- APIs: `planner_llm`, `query_prompt`, `SavedCompletions`, `save_completions`, `saved_completions`,
  `multi_query_retriever`, `generated_queries` in `pipeline/eval/multi_query.py`;
  `llama-index-llms-ollama` added
- Database: `data/_index/planner/gemma4-26b.jsonl` (gitignored); run in
  `docs/eval/runs/*-multi-query-rrf-exact`

## RET-7b  The query prompt: keep the question's details  ✅

**Status:** Done (measured; not adopted)

**Why:** RET-7 lost 42 relevant documents, and 35 of them were found by none of the 3 generated
queries, only by the question. LlamaIndex's default prompt asks for queries "related to" the
question, and gemma4 made them generic: qst_0064's "remediation timeline … proposed for the
upcoming external pen test" (v1 rank 5) became "standard timeframe for fixing high vs low severity
security vulnerabilities". In questions that lost documents, the generated queries were less
similar to the question (cosine 0.724 vs 0.755 on average).

**What changed:** only the prompt (`multi_query_retriever(..., prompt=)`), two tried:
- `PERSPECTIVE_PROMPT`: the RAG-Fusion / LangChain `MultiQueryRetriever` style, "vary the wording
  and perspective".
- `KEEP_DETAILS_PROMPT`: keep every name, product, project, team, customer, number, date and
  quoted term; change only the wording; self-contained queries. Built from what enterprise RAG
  write-ups recommend (keep entities, time ranges and IDs; no vague references).

Both keep qst_0064's "upcoming external penetration test"; neither splits qst_0436 by SDK. Planned
locally by gemma4:26b (639 s and 745 s for 470), the 2,820 new queries embedded by voyage-4
(89,796 tokens, $0.0054).

| before reranking (exact) | recall@50 | recall@20 | recall@10 | mrr@10 | gained | lost | completeness@50 | project@50 | semantic@50 |
|---|---|---|---|---|---|---|---|---|---|
| v1: the question alone | 0.838 | 0.791 | 0.722 | **0.622** | | | **0.651** | 0.801 | 0.696 |
| default prompt (RET-7) | 0.818 | 0.746 | 0.701 | 0.577 | 21 | 42 | 0.603 | 0.768 | 0.648 |
| perspective | 0.838 | 0.772 | 0.721 | 0.610 | 16 | 17 | 0.597 | 0.826 | 0.696 |
| **keep-details** | **0.848** | **0.797** | **0.736** | 0.618 | 17 | 9 | 0.626 | **0.834** | **0.728** |

("gained" and "lost": relevant documents in the top 50 that v1's top 50 does not have, and the
reverse.) What it says: the loss was the prompt, not multi-query. Keeping the details turns
−0.020 recall@50 into +0.010, gaining more than it loses, with the biggest gains in semantic and
project questions. Completeness is still below v1 (0.626 vs 0.651): rephrasing does not split a
multi-part question; that needs decomposition.

**After reranking** (rerank-3-lite on the keep-details top 50: 11,421,145 tokens, 165 s, free
pool):

| exact, reranked | recall@5 | recall@10 | recall@20 | hit@10 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|---|
| v2: v1 top 50 + rerank-3-lite | 0.777 | 0.800 | 0.820 | 0.851 | 0.112 | 0.785 | 0.762 |
| keep-details top 50 + rerank-3-lite | **0.786** | **0.807** | **0.827** | **0.864** | 0.112 | **0.795** | **0.769** |

Recall@10 by source, v2 → keep-details: Linear 0.826 → **0.891**, Fireflies 0.645 → 0.665, Google
Drive 0.748 → 0.767, HubSpot 0.765 → **0.735**, Jira 0.823 → 0.819, GitHub 0.781 → 0.779, the rest
within 0.001. By type: semantic 0.688 → **0.720**, conflicting_info 0.825 → 0.850, completeness
0.576 → **0.545**, project_related 0.634 → 0.622, basic 0.851 unchanged.

Question by question (k = 10): recall is better for 13, worse for 11 and the same for 446; the mean
gain +0.007 has a 95% bootstrap interval of [−0.008, +0.022] (MRR +0.010, [−0.003, +0.023]).

**Verdict: not adopted; v2 stays.** The gain is within noise, while multi-query adds a planner
call (~1.4 s a question locally) and 4× the searches. It moves recall between question types
(semantic up, completeness down) more than it raises it. Completeness, the weakest type, needs
the question split per part (decomposition), which rephrasing does not do.

**Dependencies**
- APIs: `PERSPECTIVE_PROMPT`, `KEEP_DETAILS_PROMPT`, `prompt=` on `query_prompt`,
  `save_completions` and `multi_query_retriever` in `pipeline/eval/multi_query.py`
- Database: `data/_index/planner/gemma4-26b-{perspective,keep-details}.jsonl` (gitignored); runs
  in `docs/eval/runs/*-multi-query-{perspective,keep-details}-rrf-exact`

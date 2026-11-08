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
| RET-8  a deeper pool for the reranker: top 200 reranked, recall@10 0.800 → 0.853 | ✅ |
| RET-9a  `titles_like`: every document whose title matches, capped with a total; the agent loop's `list` tool | ✅ |
| RET-9b  `container_of`: Linear/Jira project key from the raw filename, the one real container in the data | ⬜ |
| RET-10  the agentic retrieval loop: 10a `search_snippets` ✅ · 10b `read_document` ✅ · 10c `retrieval_agent`, `AGENT_PROMPT` ✅ · 10d-a run helpers ✅ · 10d-b `agent_answers` ✅ · 10e-a `claude_llm` · 10e-b cut list groups · 10e-c stop prompt · 10e first measured run (69 + 50 controls, then all 500 on the official judge) | ⬜ |

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

## RET-8  A deeper pool for the reranker: top 100 and top 200  ✅

**Status:** Done (measured; v3 pending a decision on latency)

**Why:** the reranker only re-sorts what it is given, and 161 relevant documents never reach
v1's top 50. It sorts well (v2: recall@10 0.722 → 0.800 on the same 50), so hand it more.

**What changed:** only depth. v1's dense and BM25 retrievers each return 200 chunks, RRF fuses
them (`hybrid_retriever(..., "rrf", top_k=200)`, exact), and the first 100 or all 200 go to
rerank-3-lite. No new code: `rerank_saved` and `replay_retriever` as in RET-5. Searching 470
questions 200 deep took 42 s ($0); the top 200 is saved in `data/_index/rerank/v1_top200_candidates.jsonl`.

Recall of the fused list before reranking (by document, 470 questions):

| candidates | overall | semantic | project | completeness | Fireflies | Linear | HubSpot |
|---|---|---|---|---|---|---|---|
| top 50 (v1, 50-deep lists) | 0.838 | 0.696 | 0.801 | 0.651 | | | |
| top 50 (200-deep lists) | 0.850 | 0.728 | 0.830 | 0.663 | 0.690 | 0.868 | 0.765 |
| top 100 | 0.878 | 0.768 | 0.878 | 0.669 | 0.730 | 0.951 | 0.765 |
| top 200 | **0.913** | **0.840** | **0.922** | 0.711 | **0.840** | **0.983** | 0.765 |

Deeper lists alone lift the top 50 (0.838 → 0.850): a chunk ranked 60th by one retriever still
earns its RRF share. HubSpot does not move at any depth: those misses are not a depth problem.

After rerank-3-lite:

| exact, reranked | rerank tokens | recall@5 | recall@10 | recall@20 | hit@10 | precision@10 | mrr@10 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|
| v2: top 50 | 11,524,826 | 0.777 | 0.800 | 0.820 | 0.851 | 0.112 | 0.785 | 0.762 |
| top 100 | 23,062,492 | 0.809 | 0.832 | 0.851 | 0.883 | 0.115 | 0.806 | 0.787 |
| **top 200** | 46,017,479 | **0.827** | **0.853** | **0.867** | **0.902** | **0.118** | **0.826** | **0.807** |

Question by question against v2 (k = 10): top 100 is better on 21 and worse on 5, recall@10
+0.033 [95% bootstrap +0.017, +0.050], MRR +0.021 [+0.008, +0.036]; top 200 is better on 34 and
worse on 7, recall@10 **+0.053 [+0.032, +0.076]**, MRR +0.041 [+0.024, +0.060]. Both intervals
exclude zero: a real gain, unlike RET-7b.

Recall@10 by source, v2 → top 200: Linear 0.826 → **0.915**, Google Drive 0.748 → 0.824, Fireflies
0.645 → 0.705, Confluence 0.717 → 0.767, Jira 0.823 → 0.861, GitHub 0.781 → 0.814, Gmail 0.791 →
0.831, Slack 0.777 → 0.807, HubSpot 0.765 unchanged. By type: semantic 0.688 → **0.808**, basic
0.851 → 0.903, project_related 0.634 → 0.655, completeness 0.576 → 0.583.

**The price:** 4× the rerank tokens per question (~98K vs ~23K) and ~4× the rerank time. The
free-pool run hit Voyage's limit of 4M rerank-3-lite tokens a minute when top 100 and top 200
ran together; top 200 alone waits out the limit.

**What it says:** depth is the biggest step since reranking itself (+0.053). The distractors of a
deeper pool cost less than the documents it adds. Completeness and HubSpot barely move: they
need different fixes (decomposition; a HubSpot-specific look).

**With RET-7b's 3 keep-details queries, 200 deep** (search only, 136 s, $0): pool recall at top
50 / 100 / 200 goes 0.851 / 0.879 / 0.914 (question alone) → 0.853 / 0.888 / 0.914, gaining 7 and
losing 8 relevant documents at top 200. A deep pool already holds what the extra queries find,
so they were not reranked: top 200 with the question alone, no LLM planner, is the candidate.

**Dependencies**
- APIs: `hybrid_retriever(..., top_k=200)`, `rerank_saved`, `voyage_rerank`, `replay_retriever` (unchanged)
- Database: `data/_index/rerank/v1_top{100,200}_candidates.jsonl`, `top{100,200}-rerank-3-lite.jsonl`
  (gitignored); runs in `docs/eval/runs/*-rrf-top{100,200}-rerank-3-lite`

---

## RET-9a  `titles_like`: list every document whose title matches, for "all / every / how many" questions  ✅

**Status:** Done

**As a** RAG developer
**I want to** one function that lists every document of a source whose title contains a
pattern: `(source_type, doc_id, title)` rows plus the total count, capped
**So that** an agent can enumerate a set ("all incident postmortems", "every Project Orion
weekly update") instead of sampling it with top-k search, which is where recall is lost today

**Why this story.** Search returns a sample, not a set. 19 of the 470 questions with gold
documents ask for all/every/how many; their official-judge recall is 79.4% (13 full, 2 zero)
and their score 56.5 against 76.9 overall. On 16 of the 19 every gold document is one source,
and the gold documents share a **title family**: the text before the first `:`, ` — ` or ` (`.
The corpus has 6,230 title families of two or more documents covering 330,074 of 511,962 rows.
A Slack document's title *is* its channel (36 channels on 273,519 of 285,605 rows), so the same
function lists a channel. This is the first tool of the agentic retrieval loop (see
[pipeshub-design] in `docs/design/`, to be written with RET-10); the others are search, read
and grep. It is also how PipesHub (leaderboard #1) answers enumeration questions: "one search
returns a sample, not the set: list the records of the folder".

Glossary:
- **Title family**: documents whose titles share the part before the first `:`, ` — ` or ` (`,
  e.g. 38 Confluence pages `Postmortem: …`. Not a field in the data; a pattern over titles.
- **Container**: where a document lives at its source (Slack channel, Linear/Jira project key,
  Confluence space, Drive folder). Only Slack (title) and Linear/Jira (raw filename key, RET-9b)
  carry one; Confluence, Drive, GitHub, Gmail and Fireflies do not, anywhere in the data
  (audit 2026-11-08: `Space:` in 3 of 5,189 Confluence pages, `Folder:` in 1 of 25,108 Drive files).

**Acceptance Criteria (Gherkin)**
- Given the document table, source `confluence` and pattern `Postmortem`, Then every row
  whose title contains it, case-insensitive, as `(source_type, doc_id, title)` in title order, and
  `total` = the number of rows; no row from another source
- Given a pattern that matches more rows than `limit` (default 200), Then the first `limit`
  rows and the full `total`, so the caller knows the list was cut and can narrow the pattern
- Given a source of `None`, Then all sources are searched and each row keeps its own source
  (a `doc_id` can appear in two sources: 3 ids do; the row is `(source_type, doc_id, title)`)
- Given a pattern nothing matches, Then no rows and `total` 0
- Given a row with an empty title (15 Slack rows), Then it never matches
- Given the real table, Then `titles_like(t, "confluence", "Postmortem")` returns 73 rows
  that include all 9 gold documents of qst_0437, and `titles_like(t, "slack", "eng-security")`
  returns 200 rows with `total` 12,432 (82 path-style titles such as `slack/eng-security/…json`
  contain the channel name; the channel itself is 12,350 rows)

**Example with real data**
qst_0437 "Across all incident postmortems, which Redwood team was assigned the most follow-up
action items?" has 9 gold documents and recall 0.0 with today's hybrid search + rerank: the
question's words ("team", "follow-up action items") match no single postmortem better than the
other postmortems: every one has an action-items section. Their titles:

    Postmortem: Streaming stalls during peak traffic (2026-01-12)
    Postmortem: Latency regression after tokenizer update (2026-01-27)
    Postmortem: Rate limit misconfiguration caused elevated 429s (2026-02-…)
    P0 Incident Postmortem: … (2 of the 9)

Before: the loop submitted 40 documents (Slack `postmortems` and `incidents` messages, Gmail
incident threads), 0 of 9 gold. After: `titles_like(t, "confluence", "Postmortem")` → 73 rows,
all 9 inside (38 start with `Postmortem:`, 2 gold ones with `P0 Incident Postmortem:`, the rest
are playbooks and templates that name postmortems); the agent reads the 73 titles (one line
each, ~2.5K tokens) and fetches the ones the question needs. Same for qst_0439 (5 gold, all `Postmortem:`, recall 60%) and qst_0435
(6 gold `Project Orion — Weekly status update (date)`, a family of exactly 6). Where it does
not help: qst_0444 (6 gold pages, 6 different families) and qst_0450 (8 Fireflies calls with
unrelated titles: that one needs grep on "residency", a later story).

Cost: the title column is 511,962 short strings, read once from `data/_full/documents.parquet`
(pyarrow, no content column); a match is a vectorised `match_substring` over it, milliseconds,
no index, no model call, $0.

**Decisions**
- Case-insensitive substring, not an anchored prefix or a regex: the prefix `Postmortem:` gives 38
  rows but misses the 2 `P0 Incident Postmortem:` gold pages; a regex is more precise but the
  model writes it and an empty list gives no signal why. Can be added later as a parameter.
- Substring on the title, not a derived container table: the families that matter
  (`Postmortem`, `Project Orion`) are title patterns, and five of nine sources have no
  container field at all. RET-9b adds the one real container the data has (Linear/Jira key).
- A cap with the total, not an error: the agent sees "200 of 12,432" and narrows, the same
  way a human would with a folder of 12,000 files.
- Rows carry `source_type` because `doc_id` is not unique across sources (3 collisions).

**Non-functional Requirements**
- Shared NFRs. Deterministic, $0, no network. Reuse: the table comes from
  `parquet_documents`' source file; pyarrow `compute.match_substring(ignore_case=True)` does the
  match, no custom loop. Returns a NamedTuple `TitleList(rows, total)`.
- Audit (2026-11-08, real corpus): 19 of the 470 questions with gold ask for all/every/how many;
  for 11 of them every gold document sits in one title family of ≤ 200 titles. A cap of 200
  lists 6,171 of the 6,230 families with ≥ 2 documents whole (50 lists 6,096; 500 lists 6,191).
  Measured by `tests/test_eval_titles.py` on the real table: 73 rows / 9 of 9 gold for
  qst_0437; 200 rows of 12,432 for the Slack channel.

**Dependencies**
- APIs: `titles_like(table, source_type, pattern, limit=200) -> TitleList` in
  `pipeline/eval/titles.py`; `document_titles(path) -> pyarrow.Table` loading `doc_id`,
  `source_type`, `title` only
- Service Bus: N/A · Database: reads `data/_full/documents.parquet` · UI: N/A
- Blocks: RET-10 (the agent loop's `list` tool wraps this function as a `FunctionTool`)

## RET-9b  `container_of`: Linear/Jira project key from the raw filename  ⬜

**Status:** To do

**As a** RAG developer
**I want to** the one container the data really carries, the Linear/Jira project key
(`ENG`, `PM`, `DES`, `SUP`, `INT`), as a `(source_type, doc_id) -> key` table built from the raw
filenames `dsid_<id>__<KEY>-<n>-<slug>.txt`
**So that** `titles_like` can be narrowed to a project ("every SUP ticket about …") where titles
alone cannot, since only 3 of 41,428 Linear/Jira titles contain their key

**Acceptance Criteria (Gherkin)**
- Given `dsid_2fd1dda7…__SUP-613947-unexpected-429s.txt`, Then `("jira", "dsid_2fd1dda7…", "SUP")`
- Given a Linear file with no key (`…__suggestions-risk-badge-visual-exploration.txt`, 1 of 35,308),
  Then key `None`, never an exception
- Given the real archives, Then 35,307 Linear and 6,120 Jira rows with a key; prefix counts
  ENG 23,168, PM 8,703, DES 3,436, SUP 4,584, INT 1,536 (the audit row)
- Given the one doc_id with two Jira files (`dsid_6df52fdb…`, INT-7832 twice), Then both rows kept

**Example with real data**
Jira titles read "Log retention exception  Northstar Bank (disable prompt/completion log …)";
the key `SUP-…` is only in the filename. Before: no way to list "all SUP tickets". After:
`titles_like` rows joined to this table give 4,584 SUP tickets, narrowable by title pattern.

**Non-functional Requirements**: shared NFRs; a pure function over filenames plus one scan
of the archive listings; writes `data/_index/containers.parquet` (gitignored).

**Dependencies**: APIs `container_of(filename) -> Optional[str]`, `write_containers(archives, out)`
in `pipeline/eval/titles.py` · Database: `data/_index/containers.parquet` · Blocks: nothing;
RET-9a and RET-10 work without it.

---

## RET-10  The agentic retrieval loop: search, read, list, answer from what was read  ⬜

**Status:** To do (split into 10a to 10e below; each merges alone)

**Why this story.** Today's retrieval is a fixed script: hybrid search, rerank, a CRAG verdict,
gap queries, search again, then hand the top documents to the answerer. It reaches document
recall 90.27% and the official judge-only score 76.94 (v4 answers). The 69 questions with
recall below 100 miss 126 gold documents; measured on the saved top-200 (audit 2026-11-08):

| where the missed gold document ranks (reranked) | docs |
|---|---|
| 1–10 (retrieved, cut by the safe rule) | 10 |
| 11–50 | 27 |
| 51–200 | 25 |
| not in the top 200 | 64 |

Half are already in the candidate pool and need a reader that looks past the first few; the other
half need a *different query*: in 29 questions every missed document is outside the top 200, and
the question's words never reach it. One identifier question (qst_0341, "SLOs") would be found by
an exact-string search; every ticket key and customer name in the 69 questions already appears
in a submitted document, so grep is not a recall lever here and is left out of RET-10.

What is: an agent that reads whole documents, writes down which parts of the question are still
unanswered, searches again in the vocabulary of the documents it read, lists a title family when
the question asks for all/every/how many (RET-9a), and stops when every part has a quote or after
8 tool calls. It submits only the documents it read: the 401 full-recall questions submit 5.12
documents today of which 1.22 are gold (3.90 extras; 294 questions carry exactly 2), the
leaderboard's #1 submits 0.4 extras. This is PipesHub's design (leaderboard #1, 93.24) and A-RAG's
(arXiv 2602.03442: hierarchical tools beat a single-search agent on every dataset and use a tenth
of its tokens); see `docs/design/` note "agentic-rag-best-practices" in the memory of 2026-11-08.

Glossary:
- **Agent loop**: the model is called repeatedly; each call either picks one **tool** (a Python
  function it can call with arguments) and gets the result back, or writes the final answer.
  LlamaIndex's `FunctionAgent` runs this loop with Claude's native tool calling.
- **Iteration**: one model call plus the tool call it makes. `max_iterations` caps the loop.
- **Ledger**: the set of document ids the agent has read in full. The submitted document list.
- **Record / replay**: every tool call's arguments and result are saved to a file on the first
  run; a later run answers from the file, so tests and re-scores cost $0 and are deterministic
  (the pattern of `SavedCompletions` in `multi_query.py` and `ReplayRetriever` in `rerank.py`).

**Non-functional Requirements (all sub-stories)**: shared NFRs. Determinism through record/replay.
Every tool call emits an observability event (`pipeline/observability.py`), never a print. The
agent prompt is generic: nothing about question types, gold answers or the judge. Budget per
question: 8 iterations, 3 reads. Cost is estimated and approved before the first paid run.

## RET-10a  `search_snippets`: the search tool's text, one block per document  ✅

**Status:** Done

**As a** RAG developer
**I want to** the existing retriever's ranked chunks turned into the text a tool returns: one
block per document (title, source, doc_id, how many chunks matched) with its best two chunks as
400-character snippets, documents in the order of their best chunk, at most 10 documents
**So that** the agent sees candidates with their ids and enough text to decide what to read, in
about 1.6K tokens, instead of 50 bare chunks of 512 tokens

**Acceptance Criteria (Gherkin)**
- Given ranked chunks where one document holds chunks ranked 1, 2 and 8, Then it is one block with
  its two best chunks and the document count is not inflated
- Given 14 chunks over 10 documents, Then 10 blocks in best-chunk order (the GEN-2a rule)
- Given a `source` filter, Then only chunks of documents of that source are kept, before the cut,
  so the 10 slots stay full (the source comes from the title table, RET-9a; replayed chunks carry
  no metadata)
- Given a document already in the ledger, Then its block says `(read)`; one shown by an earlier
  search of the same question says `(seen)` (PipesHub: shown passages give way to new ones)
- Given a chunk that starts with its document title, Then the snippet starts after it; a snippet
  longer than 400 characters ends with `…`; newlines become spaces
- Given a doc_id the title table does not know, Then `(no title) | ?`, never an exception
- Given no chunks at all, Then the one line `No documents matched.`, so the model gets a sentence
  to act on, not an empty string
- Given a document both read and seen, Then `(read)` alone: it says more
- Given the saved reranked top 200 and qst_0001, Then 10 blocks, the first the gold document
  with `3 chunks matched, 2 shown`, and the text under 2,500 tokens

**Example with real data**: qst_0001 ("default size limits for file uploads …"): the gold
document's chunks rank #1, #2 and #8 (GEN-2a); 14 chunks hold 10 documents. Before: 14 chunk
texts of ~2,350 characters. After: 10 blocks, the first
`[1] add multipart/form-data handling, … | github | dsid_ae068ee4… | 3 chunks matched, 2 shown`
with the rank-1 snippet (the PR description) and the rank-2 snippet (the review thread), about
1.6K tokens in all.

Measured on all 470 questions (saved reranked top 200, 2026-11-08): 10 documents are reached at
chunk rank 11 (median, max 26); 129 questions have a top-10 document with 3 or more chunks in that
window; 46,509 of 91,496 chunks start with their title (40,716 of 83,823 distinct chunks); in 90 of
those the title is only a word prefix (`incidents` before `incidents-bot: …`), so the strip needs
the next character to be a line end or a colon. Output per search, median / p90 tokens:
2 full chunks per document 6,656 / 9,249; 1 full chunk 5,095 / 5,756; 2 × 800 characters
2,912 / 3,897; **2 × 400: 1,615 / 2,118** (chosen); 1 × 400: 1,287 / 1,351.

**Decisions**
- Snippets of 400 characters, two per document: a chunk is ~512 tokens and the agent reads the
  document in full anyway (RET-10b), so a long preview is paid twice. PipesHub's own note:
  search passages were most of a question's cost, and missing details sat in parts the search did
  not show; the fix was a focused read, not longer previews.
- The block says how many chunks matched (`3 chunks matched, 2 shown`): the agent learns there is
  more to read without being shown it.
- A pure function over ranked chunks plus a title map, not a function that calls the retriever:
  testable on the saved candidates at $0; RET-10c wraps it with the live retriever.

**Dependencies**: APIs `search_snippets(ranked, titles, source=None, read=(), seen=(), documents=10,
per_document=2, snippet_chars=400) -> str`, `snippet_of(text, title, chars)` in
`pipeline/eval/agent_tools.py`; `titles` is `{doc_id: (source_type, title)}` from `document_titles`
(RET-9a); the ranked chunks come from `live_retriever` + `live_reranker` (GEN-8a) or
`replay_retriever` (RET-5) · Database: none · UI: N/A

## RET-10b  `read_document`: a whole document by id, with a window for the long ones  ✅

**Status:** Done

**As a** RAG developer
**I want to** the title and content of one document by `doc_id`, whole when it fits, else a
window of `chars` from `start` with a line saying how much follows
**So that** the agent answers from the full text, where today's chunk-level misses (part of a
list, a step without its condition) come from

**Acceptance Criteria (Gherkin)**
- Given a document of 2,904 characters and a cap of 30,000, Then the whole content and no
  trailing note
- Given a 41,317-character document, Then the window ends at the last line break before
  30,000 and the line `… 11,3xx more characters; call again with start=<that position + 1>`
  (a transcript line is never split; with no line break inside the window, a hard cut)
- Given `start=30000` on it, Then the rest and no note; given a start past the end, Then
  `<id> has 41317 characters; nothing after <start>`
- Given an empty title (15 Slack rows), Then the heading is the id
- Given an id not in the cache and a corpus path, Then one scan fills the cache and a second
  read never touches the file
- Given an unknown id, Then the text `No document with id dsid_x`, never an exception (the agent
  may mistype an id)
- Given one of the 4 ids that name two documents, Then both texts, the second after a separator
  (the `documents_by_id` rule, GEN-2b)

**Example with real data**: document length is small: p50 4,276 characters, p99 11,846, and only
22 of 511,962 exceed 30,000 (all Fireflies transcripts; the longest, `dsid_5bc9e06d…` "Incident
taxonomy working session (v1)", 41,317). The 9 gold pages of qst_0437 are 1,654 to 2,904
characters, 18.6K in total, so an agent reads all nine in about 5K tokens.

**Decisions**
- A dict cache plus the parquet as fallback, not a scan per read: a cold read scans the 1.4 GB
  single-row-group parquet in 2.1 s (measured 2026-11-08; GEN-2b saw 1.2 s on an idle machine),
  which would be about 12 minutes of scanning for 119 questions at 3 reads each. RET-10d
  prefetches each question's candidate documents in one scan, the GEN-2b pattern, so the scan
  happens only for ids that came from `list`. A SQLite store would be faster still; not needed
  while the cache covers the common case.
- The window ends at the last line break: the 22 long documents are Fireflies transcripts of
  `[mm:ss] Speaker:` lines, and a hard cut at 30,000 splits a sentence across two reads.

**Dependencies**: APIs `read_document(doc_id, documents, parquet_path=None, start=0, chars=30_000)
-> str` in `pipeline/eval/agent_tools.py`, `documents` being `{doc_id: (title, content)}`; reuses
`documents_by_id` (GEN-2b) for a miss · Database: `data/_full/documents.parquet` · UI: N/A

## RET-10c  `retrieval_agent` and `AGENT_PROMPT`: the loop  ✅

**Status:** Done

**As a** RAG developer
**I want to** a LlamaIndex `FunctionAgent` over three `FunctionTool`s (search → RET-10a, read →
RET-10b, list → RET-9a `titles_like`), a ledger of read ids kept in the agent's state, a budget
of 8 iterations, and one generic system prompt
**So that** the model decides what to search, read and list, and the answer rests on documents
it read

**Acceptance Criteria (Gherkin)**
- Given a fake LLM that calls search, then read on the first id, then answers, Then the ledger
  holds that one id and the answer is returned with it
- Given a fake LLM that never stops, Then the loop ends after 8 iterations and the answer is
  written from what was gathered (A-RAG's forced synthesis), with `budget_exhausted` true
- Given a read of an id already in the ledger, Then the tool returns `already read` at no cost
- Given parallel tool calls in one step, Then all results return in one message (Claude's rule)
- Given the prompt text, Then it contains no question id, gold text, question type or judge word
- Given the three tools, Then they are named `search`, `read`, `list_titles` with descriptions the
  model reads, and `list_titles` prints the total then one `doc_id | title` line per row

**The prompt (generic, PipesHub's rules in our words)**: search first with a short query; read in
full the 1 to 3 documents the answer will rest on; list which parts of the question still have
no quote and search again for each in the words the documents use (system, team, customer, ticket
id), not the question's; for "all / every / how many", list the titles instead of searching; stop
when every part has a quote; answer only from documents you read, values verbatim with their
qualifiers, a procedure from one document; when two documents disagree about the same thing,
prefer the explicit supersession, then the narrower scope, then the most recent, and say so in
a few words.

**Example with real data** (spike 2026-11-08: the real tools on the saved candidates, title table
and corpus, driven by a scripted LLM): `search("incident postmortem follow-up action items owner")`
→ 5,247 characters, 10 Slack/Gmail blocks, no gold; `list_titles("confluence", "Postmortem")` →
8,210 characters, 73 titles, all 9 gold inside; three `read` calls in one step → 2,969 / 2,279 /
2,332 characters, one iteration; answer. 4 of 8 iterations, ledger = the 3 read ids, 4.6 s with
cold parquet scans. The script stopped at 3 reads; a real model is expected to read the 9 dated
`Postmortem: …` pages. Expected trace as written before the spike: `search("incident postmortem follow-up
action items")` → 10 blocks, Slack `postmortems` and `incidents` messages; the model sees no
Confluence postmortem and the word "all"; `list("confluence", "Postmortem")` → 73 titles; `read`
on the dated `Postmortem: …` pages (up to the budget of 3 reads per step, 9 in 3 steps); answer
with the team counted. Submitted: the 9 read ids. Today: 40 ids, 0 gold.

**Decisions**
- The model sees one line of state each step, `Documents read so far: {'read': [...]}`, not the
  library's dump of the whole state; the seen ids live under a separate store key.
- The answer keeps prompt v3's shape, `<quotes>` then `<answer>`, so `answer_of` / `quotes_of`
  (GEN-13b) parse it and the quotes-first habit that lifted completeness in v4 stays.
- "Read 1 to 3 documents per step" is a prompt rule; the hard budget is `max_iterations=8`, which
  LlamaIndex enforces, with `early_stopping_method="generate"` so the budget ends in an answer
  (the default `"force"` raises).
- A mistyped id (`No document with id …`) never enters the ledger; a repeated read returns
  `already read` without touching the corpus.

**Dependencies**: APIs `retrieval_agent(llm, tools) -> FunctionAgent`,
`agent_tools(retriever, titles, table, documents, parquet_path) -> list[FunctionTool]`,
`answer_question(agent, question, max_iterations=8) -> AgentAnswer(answer, quotes, read,
iterations, budget_exhausted)`, `titles_text`, `AGENT_PROMPT`, `STATE_PROMPT`, `MAX_ITERATIONS` in
`pipeline/eval/agent.py`; LlamaIndex `FunctionAgent`, `FunctionTool`, `Context` state; Claude via
`llama_index.llms.anthropic.Anthropic` with `thinking_dict={"type": "adaptive"}` and
`additional_kwargs={"output_config": {"effort": "medium"}}`; never `tool_required` (the wrapper
would send a forced tool choice, rejected with thinking on) · UI: N/A

## RET-10d  `agent_answers`: run the loop over questions, resumable, traced  ✅

**Status:** Done, in two PRs. **10d-a** ✅ (helpers: `usage_of`, `candidate_ids`, `candidate_prefetcher`,
`finished_rows`) · **10d-b** ✅ (`agent_answers`, the trace sidecar, the `on_event` hook in
`aanswer_question`)

**As a** RAG developer
**I want to** one row per question `{question_id, answer, document_ids, quotes, iterations,
budget_exhausted, input_tokens, output_tokens}` appended to a JSONL as each finishes, questions
already there skipped, each batch's candidate documents prefetched in one scan, and every tool
and model call written to a trace sidecar
**So that** a crash never repeats a paid question, reads do not scan the corpus, and a wrong answer
can be explained from its trace without re-running anything

**Acceptance Criteria (Gherkin)**
- Given 2 questions and a fake agent, Then 2 rows, flushed one at a time
- Given a re-run, Then no agent call and 0 rows added
- Given a trace sidecar, Then one line per question with every tool call (name, arguments,
  result size) and the model-call count
- Given `document_ids`, Then it is the ledger (read ids) in read order, never the search hits
  (the test's search hits one document and the agent reads another)
- Given the row, Then it is the shape the judge (`question_id`, `answer`) and the official scorer
  (`question_id`, `answer`, `document_ids`) read; extra keys are ignored
- Given a prefetch and a batch size, Then prefetch is called once per batch with its question ids
- Given a crash on the second question, Then the first row is on disk and a re-run answers only the
  second; given a last line cut mid-write, Then it is dropped and appends stay well-formed
- Given the whole run, Then one event loop: the Anthropic wrapper's async client keeps sockets
  bound to the loop that opened them, so a loop per question fails on the second question
- Given raw model responses with usage, Then input and output tokens are summed per question; 0 when
  the provider (or the test mock) reports none

**10d-a, measured 2026-11-08**: the saved top-200 candidates hold a median of 179 distinct documents
per question; 10 questions prefetch 1,671 documents (10.5 MB) in one 3.7 s scan; all 470 at once
would be 67,823 documents, about 290 MB. `finished_rows` drops a last line cut by a crash and
rewrites the file, so a resumed run appends cleanly. `usage_of` counts cached reads and cache writes
into input (Anthropic reports them apart from `input_tokens`).

**Decisions (10d-b)**
- A trace sidecar, not a replay of the model: the model is the nondeterministic part and nothing
  downstream needs a byte-identical re-run; the answers file is what every judge and report reads,
  and a question is paid for once (resume). Same contract as `save_answers` and `rerank_saved`.
- Prefetch per batch of 10 from the saved candidates; ids outside them (from `list_titles`) use
  RET-10b's lazy scan.
- The trace line is written before the row, so a crash between the two leaves a trace without an
  answer, which the resume redoes, never an answer without a trace.

**Dependencies**: APIs (10d-a) `usage_of(raw)`, `candidate_ids(candidates_path)`,
`candidate_prefetcher(candidates, documents, parquet_path)`, `finished_rows(path)`; (10d-b)
`agent_answers(agent, questions, out_path, trace_path, prefetch=None, batch=10, max_iterations=8)
-> int` in `pipeline/eval/agent_run.py`, `aanswer_question(..., on_event=)` in `pipeline/eval/agent.py`;
pattern of `save_answers` (GEN-2e) and `rerank_saved` (RET-5) · Database:
`data/_index/answers/agent-*.jsonl`, `data/_index/agent/trace-*.jsonl` (gitignored) · UI: N/A

## RET-10e  First measured run: the 69 and 50 controls, then all 500  ⬜

**Status:** To do

**As a** RAG developer
**I want to** the loop run on the 69 questions with recall below 100 plus 50 full-recall
controls, judged by the Claude judge against the same questions' v4 answers; then, if recall rises
and the controls hold, all 500 through the official judge-only batch (~$5)
**So that** the change is measured on the official ruler before it becomes the default

**Acceptance Criteria (Gherkin)**
- Given the 119-question run, Then a table: document recall, extras per question, correct,
  completeness, iterations and tokens per question, for the 69 and the 50 separately, next to
  today's values (69: recall 0 to 99, 9.67 extras; 50: recall 100, 3.90 extras)
- Given the all-500 run, Then the official judge-only score next to 76.94, recall next to
  90.27%, invalid extra next to 4.75, and the result in `docs/eval/results.md`
- Given the cost estimate before each run, Then it is shown and approved first; the loop cannot
  use the Batch API (each step depends on the last)

**Success**: recall above 93% on the 69-plus-50 set with the 50 controls still at 100, extras
under 1.5; on all 500 an official score above 80.

**Dependencies**: RET-10a to 10d, RET-9a; `exp_claude_judge.py` (experiments) or
`pipeline/eval/judge.py`; the official scorer staging in the session scratchpad · UI:
`docs/eval/report.html` gets the run

---

## RET-10e preparation: what the first live run showed  (10e-a, 10e-b, 10e-c)

The smoke run of 2026-11-08 (the loop live on qst_0437 and qst_0001, Haiku 5.5, live hybrid
search + Voyage reranker; script `data/_index/experiments/agent_smoke.py`) proved the plumbing
and found three things the measured run (RET-10e) cannot start without. Each is one function.

- qst_0001: correct, recall 1/1, 5 to 7 model calls, about half a cent. The run-to-run variance is
  real: a second run took 7 calls and read 8 documents where the first took 5 and read 6.
- qst_0437: recall 1/9, 11 documents submitted, budget exhausted at 9 calls, 268K input tokens, and
  the forced answer said "I have not searched or read any postmortem documents", which was false.
  Its second call was `list_titles(source=null, pattern="postmortem")`: 1,468 titles match, the
  tool showed the first 200 in title order (linear 65, gmail 42, google_drive 38, slack 33,
  fireflies 14, github 4, confluence 4) and nothing told the model the list was cut.
- Before any model call, the LlamaIndex Anthropic wrapper (0.12.2) failed twice: it does not know
  `claude-haiku-5-5` (its context-size table stops at Claude 4), and it still sends `temperature`,
  which the Anthropic SDK 1.11 / API 2026-10-21 removed.

## RET-10e-a  `claude_llm`: the Anthropic wrapper that works for Claude 5, with prompt caching  ✅

**Status:** Done 2026-11-08. `pipeline/eval/claude.py` (`Claude5`, `claude_llm`), `tests/test_eval_claude.py`
(8 tests, no API call). Decisions: sampling parameters are dropped for every model, not only unknown
ids, because the SDK rejects them for all; `max_tokens` defaults to 8,000 (longest agent answer so far
1,547 tokens). The smoke script (`data/_index/experiments/agent_smoke.py`, gitignored scratch) now calls
`claude_llm`, so the next live run exercises this code.

**As a** RAG developer
**I want to** one function returning a LlamaIndex `Anthropic` LLM that a Claude 5 model id works
with: a metadata table that knows the model, the removed sampling parameters never sent, adaptive
thinking and an effort level passed through, and the API's top-level prompt caching on
**So that** the agent (RET-10c) and the judge (GEN-9c) call Claude through the library component,
and a loop of 8 calls pays for its growing history once, not eight times

Glossary:
- **Prompt caching**: the API keeps the prefix of a request (tools, then system prompt, then
  messages) and a later request with the same prefix reads it at a tenth of the input price
  instead of re-reading it. With the top-level `cache_control` field the API caches up to the
  last cacheable block automatically, so an agent loop reuses everything but its newest tool
  result. The wrapper's own `cache_idx` marks every message, and the API allows four cache
  points per request, so it is unusable for a loop.

**Acceptance Criteria (Gherkin)**
- Given `claude_llm("claude-haiku-5-5")`, Then `.metadata` reports a tool-calling chat model with a
  1M context window and the model name; no `ValueError: Unknown model`
- Given the request the wrapper builds (`_get_all_kwargs`), Then it has no `temperature`, `top_p`
  or `top_k`, has `thinking={"type": "adaptive"}`, `output_config={"effort": <level>}` and
  `cache_control={"type": "ephemeral"}`
- Given an effort argument, Then it lands in `output_config`; default `medium`
- Given a recorded live call, Then the usage of call 1 shows a cache write of the prompt and tools
  and call 2 a cache read of the same size (the smoke run: write 1,350, then read 1,350; pinned
  from the smoke log, not a test)
- Given a model id the wrapper already knows, Then it keeps the library's metadata, and the
  sampling parameters are still not sent (the SDK rejects them for every model)

**Example with real data** (qst_0001, cached rerun): per model call, `uncached | cache read |
cache write | output`: 4 | 0 | 1,350 | 62 → 2 | 1,350 | 3,421 | 263 → 2 | 4,771 | 2,696 | 390 → … →
2 | 19,016 | 1,681 | 1,547. Seven calls, 78,906 input tokens of which 58K were cache reads and 21K
cache writes; at Haiku's prices about half a cent, where the uncached run of qst_0437 spent 268K
full-price input tokens.

**Non-functional Requirements**: shared NFRs; no model call in tests (the request is inspected,
the live numbers are pinned from the smoke log). Reuse: a subclass of
`llama_index.llms.anthropic.Anthropic` overriding `metadata` and `_get_all_kwargs`, nothing else.

**Dependencies**: APIs `claude_llm(model, effort="medium", max_tokens=8_000) -> Anthropic`,
`Claude5(Anthropic)` in `pipeline/eval/claude.py` · UI: the Ask page switches to it later ·
Judge (GEN-9c) not yet: review 2026-11-08 found that `structured_predict` bypasses `_get_all_kwargs`,
that `claude-haiku-5-5` falls back to a forced tool call (`tool_choice: any`) next to adaptive thinking,
and that `judge.py` nests `temperature` under `extra_body`; the story that moves the judge handles those

## RET-10e-b  `titles_text` when the list is cut: the largest title groups, not 200 lines  ✅

**Status:** Done 2026-11-08. `title_groups(rows, top=8) -> TitleGroups(groups, singletons)` in
`pipeline/eval/titles.py`; `titles_text(result, limit=200)` in `pipeline/eval/agent.py` prints the groups when
it is given more rows than the limit, and the `list_titles` tool now calls `titles_like(..., limit=None)`.
Decisions: separators are the story's three (`:`, ` — `, ` (`; adding ` - ` and ` | ` changes no top group);
8 groups; the branch keys on the rows present, not the total, so a list already capped by `titles_like`
prints its rows as before instead of groups over a partial list; ties break by group name then source.
Measured: 1,468 matches fold in under a millisecond; all rows for 26,880 matches cost 29 ms; the cut
text is about 500 characters against 26,971 before, and the counts add up: groups shown, a "titles in
smaller groups" line, singletons. Singletons on `postmortem` are 599 with these separators (593 in the
grooming count used a wider set). Worst case measured by review: an empty pattern pulls all 511,947 rows
into Python, 0.5 s and about 490 MB over the process baseline; fine for one question at a time, to
revisit if questions run in parallel in one process. The narrowing line also tells the model to search
when a group's titles are all the same (a Slack channel), since no pattern splits those. 9 new tests plus
2 real-corpus pins.

**As a** RAG developer
**I want to** the list tool, when more titles match than it shows, to print how many matched, the
largest title groups with their count and source, and one line telling the model to narrow with
a longer pattern or a source, instead of the first 200 lines in title order
**So that** a cut list steers the next call instead of hiding what matched

Glossary: **title group** = the text before the first `:`, ` — ` or ` (` of a title (RET-9a's
title family): `Postmortem: Streaming stalls` and `Postmortem: Latency regression` are one group.

**Acceptance Criteria (Gherkin)**
- Given 1,468 matches for `postmortem` across all sources and a cap of 200, Then no title lines;
  instead the count, the groups `postmortems 560 slack`, `incident-bot 134 slack`,
  `Postmortem 38 confluence`, `Postmortem 23 linear`, … (at most 8), how many titles are in groups
  of one (599), and the narrowing line
- Given a result that fits the cap, Then the text is unchanged (RET-10c's `titles_text`)
- Given the narrowed call `list_titles(None, "Postmortem:")`, Then 128 titles, all 9 gold pages of
  qst_0437 inside; given `list_titles("confluence", "postmortem")`, Then 73

**Example with real data**: the call the model made and what it got are in the preparation note
above; the groups are measured (2026-11-08) on the 1,468 matches. Cost: one pass over the matched
rows, no model call.

**Dependencies**: `titles_like(..., limit=None)` for the full rows (RET-9a); `title_groups(rows, top=8)` in
`pipeline/eval/titles.py`; `titles_text(result, limit=200)` in `pipeline/eval/agent.py` · UI: N/A

## RET-10e-c  The stop prompt: answer from what was read, in our shape  ⬜

**Status:** To do

**As a** RAG developer
**I want to** our own text for the forced answer at the budget, in place of the library's
("Do not attempt to use any more tools. Simply summarize what you have learned"): answer the
question from the documents you read, `<quotes>` then `<answer>`, and say which parts have no
quote
**So that** a question that hits the budget still gets the evidence it gathered, in the shape the
parsers read, instead of the smoke run's "I have not searched or read any documents"

**Acceptance Criteria (Gherkin)**
- Given the agent hits the budget, Then the final model call carries our prompt and not the
  library's (the scripted-LLM test sees the text)
- Given the forced answer, Then `answer_of` and `quotes_of` parse it as for any other answer
- Given the prompt text, Then it names no question, source or score

**Dependencies**: `FunctionAgent` has no prompt field for this; it is `DEFAULT_EARLY_STOPPING_PROMPT`
in `llama_index.core.agent.workflow.prompts`, formatted with `max_iterations`. Override by
subclassing `FunctionAgent._generate_early_stopping_response` or by patching the module constant
at import, whichever the `/story` step 5 decides; `STOP_PROMPT` in `pipeline/eval/agent.py` · UI: N/A

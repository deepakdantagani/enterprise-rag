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
| RET-3b  exact dense search for evaluation; re-score dense, BM25, relative-score and RRF fusion | ⬜ |
| RET-4  v1 full run: hybrid scored, row in `results.md` | ⬜ |

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

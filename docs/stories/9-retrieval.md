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
| RET-2  BM25 alone: score keyword search on the 470 questions | ⬜ |
| RET-3  RRF fusion of dense and BM25 | ⬜ |
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

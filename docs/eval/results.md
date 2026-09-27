# Retrieval results

One row per run of `python -m pipeline.eval.baseline` (or a later variant). Every clean-up story
adds its row and must beat the baseline, or say why not. Metrics are LlamaIndex's, on the first
k distinct documents (EVAL-1), averaged over the questions that have expected documents.
Each run's full table (per question type, per source, k = 5, 10, 20) is in
`docs/eval/runs/<date>-<name>/metrics.json`, with per-question scores in `scored.jsonl` (EVAL-5a).

| date | code | run | documents | questions | hit@10 | recall@5 | recall@10 | recall@20 | precision@10 | mrr@10 | ndcg@10 | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-26 | EVAL-3d3 | `baseline_sample` | 207 | 27 | | 0.889 | 0.963 | 0.963 | | 0.854 | 0.880 | wiring check only: 207-document haystack, all `basic`; not the baseline |
| 2026-09-27 | EVAL-3e | **v0** `baseline__voyage_4` | 511,957 | 470 | 0.668 | 0.531 | **0.609** | 0.673 | 0.085 | 0.493 | 0.494 | **the baseline**: every document, no cleaning; system below |
| 2026-09-27 | RET-2 | BM25 alone, `hybrid__voyage_4__bm25` sparse | 511,957 | 470 | 0.709 | 0.587 | 0.650 | 0.721 | 0.094 | 0.560 | 0.554 | diagnostic, not a version: keyword search only (FastEmbed `Qdrant/bm25`), same chunks as v0; see [RET-2](../stories/9-retrieval.md) |

## v0: the naive baseline

The number every later story must beat is **recall@10 = 0.609**. v0 is deliberately naive: the
corpus exactly as it ships, the library defaults, nothing tuned. Every later version changes one
thing and says which.

### System

| Stage | v0 choice | Story |
|---|---|---|
| Corpus | `data/_full/documents.parquet`: 511,962 rows, all 9 sources, 2.46B chars. No cleaning. The 1 empty row (`dsid_33cbedf0…`, Slack) is skipped; 4 dsids appear twice with different content and both copies are embedded, so 511,957 distinct documents | EVAL-3a, 3g |
| Document | `Document(id_=dsid, text=content)`; `title`, `source_type` kept as metadata, never embedded | EVAL-3a |
| Chunking | LlamaIndex `SentenceSplitter(chunk_size=512, chunk_overlap=50)`, token counts by LlamaIndex's default tokenizer | EVAL-3b |
| Chunks | 1,609,717, ~3.1 per document | EVAL-3e |
| Embedding | Voyage `voyage-4`, 1,024 dimensions, batches of 128, via `llama-index-embeddings-voyageai` | EVAL-3f |
| Vector store | Qdrant 1.19.1 in Docker (16 GB), collection `baseline__voyage_4`, cosine distance, HNSW m=16, ef_construct=100 | EVAL-3d |
| Pipeline | LlamaIndex `IngestionPipeline([splitter, embed_model])`, 1,000 documents per batch; a re-run skips documents already in Qdrant | EVAL-3b, 3d1, 3d3 |
| Retrieval | Dense vector search only: `VectorStoreIndex.as_retriever(similarity_top_k=50)` chunks. No keyword search, no reranker, no query rewriting, no metadata filters | EVAL-3d3 |
| Chunks to documents | The 50 chunks collapse to distinct documents by `ref_doc_id` in rank order, cut to the first k | EVAL-1 |
| Questions | 470 of 500 in `questions.jsonl`; 30 without expected documents (`info_not_found`, `high_level`) are skipped | EVAL-2a |
| Metrics | LlamaIndex `RetrieverEvaluator`: hit rate, recall, precision, MRR, NDCG at k = 5, 10, 20; mean per question type and per source | EVAL-2b, 3c, 3h |
| Tracing | Arize Phoenix via OpenInference, project `baseline__voyage_4` | EVAL-4 |
| Answer generation | None yet: v0 measures retrieval only | |

Cost and time: ~660M Voyage tokens (200M free, the rest paid at $0.06 per 1M; estimate from
character counts), about 1.6M chunks at 80–160 chunks/s. The first run stopped at document
279,000 on the empty row (fixed in EVAL-3g) and resumed without re-embedding. Scoring the 470
questions costs ~$0.0015. Re-scoring moved MRR@10 by 0.001 (Qdrant's HNSW search is
approximate); every other number was identical.

### v0 at k = 10, per source

| source | questions | hit | recall | precision | mrr | ndcg |
|---|---|---|---|---|---|---|
| jira | 100 | 0.880 | 0.719 | 0.131 | 0.727 | 0.647 |
| github | 60 | 0.800 | 0.669 | 0.125 | 0.624 | 0.569 |
| slack | 79 | 0.759 | 0.632 | 0.109 | 0.567 | 0.529 |
| linear | 58 | 0.672 | 0.611 | 0.095 | 0.441 | 0.463 |
| google_drive | 60 | 0.683 | 0.575 | 0.098 | 0.513 | 0.482 |
| confluence | 114 | 0.763 | 0.567 | 0.141 | 0.584 | 0.488 |
| gmail | 55 | 0.636 | 0.536 | 0.085 | 0.476 | 0.445 |
| hubspot | 34 | 0.353 | 0.353 | 0.035 | 0.204 | 0.237 |
| fireflies | 25 | 0.320 | 0.265 | 0.064 | 0.195 | 0.209 |

A question counts under every source of its expected documents, so the rows add up to more
than 470.

### v0 at k = 10, per question type

| type | questions | hit | recall | precision | mrr | ndcg |
|---|---|---|---|---|---|---|
| constrained | 30 | 0.933 | 0.900 | 0.123 | 0.762 | 0.763 |
| intra_document_reasoning | 40 | 0.700 | 0.700 | 0.070 | 0.463 | 0.520 |
| miscellaneous | 20 | 0.700 | 0.700 | 0.070 | 0.675 | 0.682 |
| basic | 175 | 0.697 | 0.697 | 0.070 | 0.527 | 0.568 |
| project_related | 40 | 0.950 | 0.558 | 0.202 | 0.767 | 0.540 |
| conflicting_info | 20 | 0.600 | 0.500 | 0.095 | 0.484 | 0.428 |
| semantic | 125 | 0.440 | 0.440 | 0.044 | 0.248 | 0.293 |
| completeness | 20 | 0.850 | 0.402 | 0.225 | 0.674 | 0.426 |

### What v0 says

- The weakest sources fail in opposite ways: Fireflies transcripts are long and noisy (filler,
  topic named in another chunk), HubSpot records are short fields with little text to embed.
- `semantic` questions, the biggest group after `basic`, are found less than half the time.
- `completeness` and `project_related` find one relevant document almost always (hit ≥ 0.85)
  but under 60% of them: multi-document questions need more than top-10 dense search.

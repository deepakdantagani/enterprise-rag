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
| 2026-09-27 | RET-3b | v0 dense, exact search | 511,957 | 470 | 0.687 | 0.548 | 0.626 | 0.698 | 0.088 | 0.508 | 0.508 | v0 re-scored without HNSW approximation: the true v0; every later version is compared to this |
| 2026-09-27 | RET-4 | **v1** hybrid RRF, `hybrid__voyage_4__bm25`, exact | 511,957 | 470 | 0.777 | 0.676 | **0.722** | 0.791 | 0.102 | 0.622 | 0.619 | dense + BM25 fused by RRF (k 60), top 50 chunks; +0.096 recall@10 over v0 exact; every step in "v0 → v1, every step" below |
| 2026-09-27 | RET-6 | **v2** v1 + `rerank-3-lite` (preview) | 511,957 | 470 | 0.851 | 0.777 | 0.800 | 0.820 | 0.112 | 0.785 | 0.762 | v1's top 50 re-sorted by Voyage's cross-encoder; +0.078 recall@10 over v1 |
| 2026-09-27 | EVAL-3i | BM25 with titles, `bm25_titles` | 511,957 | 470 | 0.740 | 0.610 | 0.688 | 0.739 | 0.099 | 0.590 | 0.586 | diagnostic: each document's title opens its text (EVAL-3i), BM25 only; +0.038 recall@10 over BM25 without titles (95% CI +0.021..+0.056), HubSpot 0.574 → 0.706; replaces RET-2's BM25 in the steps below |
| 2026-09-27 | EVAL-3i, RET-8 | **v3** dense + BM25 with titles, RRF over 200-deep lists, top 100 + `rerank-3-lite` | 511,957 | 470 | 0.891 | 0.813 | **0.845** | 0.863 | 0.118 | 0.818 | 0.799 | **current version**: +0.045 recall@10 over v2; the top 100 without titles scores 0.832, with them 0.845 (+0.013, 95% CI +0.002..+0.025); HubSpot 0.765 → 0.853; dense vectors still without titles; interactive report `docs/eval/report.html` |

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

## The v3 chain, every step

Generated by `uv run python -m pipeline.eval.results_tables` from `docs/eval/runs` (EVAL-5b):
do not edit between the markers. Steps add one thing each, all searched exactly. BM25 is the
EVAL-3i index with titles; the runs without titles (RET-2 to RET-8) stay in `docs/eval/runs` and
the rows above. Bold = best in its column.

<!-- generated: EVAL-5b -->
### All sources (470 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.687 | 0.626 | 0.088 | 0.508 | 0.508 |
| 2. BM25 with titles | exact | 0.740 | 0.688 | 0.099 | 0.590 | 0.586 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.772 | 0.722 | 0.102 | 0.498 | 0.530 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.891** | **0.845** | **0.118** | **0.818** | **0.799** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.617 | 0.548 | 0.151 | 0.498 | 0.480 |
| 2. BM25 with titles | exact | 0.685 | 0.610 | 0.166 | 0.582 | 0.556 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.706 | 0.636 | 0.170 | 0.489 | 0.497 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.874** | **0.813** | **0.220** | **0.816** | **0.786** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.753 | 0.698 | 0.049 | 0.512 | 0.528 |
| 2. BM25 with titles | exact | 0.772 | 0.739 | 0.055 | 0.592 | 0.601 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.843 | 0.803 | 0.058 | 0.503 | 0.553 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.900** | **0.863** | **0.062** | **0.819** | **0.805** |

### confluence (114 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.772 | 0.572 | 0.144 | 0.591 | 0.493 |
| 2. BM25 with titles | exact | 0.851 | 0.670 | 0.171 | 0.688 | 0.590 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.833 | 0.658 | 0.168 | 0.613 | 0.542 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.930** | **0.779** | **0.190** | **0.813** | **0.725** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.754 | 0.509 | 0.246 | 0.589 | 0.464 |
| 2. BM25 with titles | exact | 0.781 | 0.528 | 0.253 | 0.679 | 0.527 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.781 | 0.540 | 0.256 | 0.605 | 0.488 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.912** | **0.723** | **0.337** | **0.810** | **0.697** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.807 | 0.626 | 0.081 | 0.594 | 0.512 |
| 2. BM25 with titles | exact | 0.886 | 0.771 | 0.101 | 0.691 | 0.625 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.886 | 0.761 | 0.101 | 0.616 | 0.578 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.930** | **0.814** | **0.104** | **0.813** | **0.739** |

### jira (100 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.900 | 0.738 | 0.135 | 0.742 | 0.665 |
| 2. BM25 with titles | exact | 0.870 | 0.732 | 0.145 | 0.764 | 0.682 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.920 | 0.780 | 0.146 | 0.650 | 0.621 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.960** | **0.834** | **0.167** | **0.911** | **0.820** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.860 | 0.688 | 0.242 | 0.735 | 0.644 |
| 2. BM25 with titles | exact | 0.860 | 0.670 | 0.234 | 0.763 | 0.650 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.870 | 0.682 | 0.232 | 0.643 | 0.578 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.960** | **0.792** | **0.296** | **0.911** | **0.798** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.910 | 0.766 | 0.073 | 0.742 | 0.676 |
| 2. BM25 with titles | exact | 0.880 | 0.789 | 0.083 | 0.765 | 0.704 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.960 | 0.851 | 0.087 | 0.653 | 0.647 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.970** | **0.875** | **0.091** | **0.911** | **0.835** |

### slack (79 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.810 | 0.684 | 0.115 | 0.596 | 0.566 |
| 2. BM25 with titles | exact | 0.684 | 0.590 | 0.111 | 0.535 | 0.506 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.810 | 0.708 | 0.123 | 0.496 | 0.494 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.873** | **0.782** | **0.139** | **0.789** | **0.742** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.709 | 0.587 | 0.200 | 0.581 | 0.529 |
| 2. BM25 with titles | exact | 0.646 | 0.510 | 0.175 | 0.530 | 0.472 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.696 | 0.568 | 0.195 | 0.480 | 0.443 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.861** | **0.746** | **0.253** | **0.787** | **0.725** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.848 | 0.737 | 0.063 | 0.599 | 0.582 |
| 2. BM25 with titles | exact | 0.696 | 0.638 | 0.065 | 0.536 | 0.524 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.861 | 0.774 | 0.072 | 0.499 | 0.517 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.899** | **0.820** | **0.076** | **0.790** | **0.754** |

### github (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.800 | 0.673 | 0.127 | 0.624 | 0.574 |
| 2. BM25 with titles | exact | 0.767 | 0.623 | 0.128 | 0.576 | 0.517 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.817 | 0.689 | 0.133 | 0.486 | 0.489 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.900** | **0.781** | **0.143** | **0.870** | **0.782** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.717 | 0.570 | 0.217 | 0.614 | 0.537 |
| 2. BM25 with titles | exact | 0.700 | 0.507 | 0.187 | 0.567 | 0.466 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.767 | 0.589 | 0.207 | 0.479 | 0.445 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.900** | **0.743** | **0.257** | **0.870** | **0.763** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.850 | 0.743 | 0.072 | 0.627 | 0.595 |
| 2. BM25 with titles | exact | 0.800 | 0.700 | 0.075 | 0.579 | 0.543 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.867 | 0.768 | 0.078 | 0.489 | 0.515 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.900** | **0.800** | **0.079** | **0.870** | **0.791** |

### google_drive (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.700 | 0.585 | 0.102 | 0.519 | 0.490 |
| 2. BM25 with titles | exact | 0.733 | 0.666 | 0.118 | 0.621 | 0.589 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.767 | 0.693 | 0.118 | 0.510 | 0.515 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.883** | **0.807** | **0.135** | **0.795** | **0.766** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.617 | 0.496 | 0.170 | 0.507 | 0.457 |
| 2. BM25 with titles | exact | 0.717 | 0.612 | 0.197 | 0.619 | 0.564 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.717 | 0.600 | 0.180 | 0.503 | 0.474 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.883** | **0.796** | **0.257** | **0.795** | **0.759** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.733 | 0.634 | 0.057 | 0.522 | 0.505 |
| 2. BM25 with titles | exact | 0.733 | 0.687 | 0.065 | 0.621 | 0.598 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.850 | 0.791 | 0.070 | 0.516 | 0.545 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.883** | **0.829** | **0.073** | **0.795** | **0.775** |

### linear (58 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.655 | 0.593 | 0.093 | 0.436 | 0.456 |
| 2. BM25 with titles | exact | 0.793 | 0.722 | 0.112 | 0.669 | 0.640 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.810 | 0.749 | 0.116 | 0.530 | 0.552 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.948** | **0.887** | **0.129** | **0.891** | **0.856** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.603 | 0.526 | 0.159 | 0.429 | 0.430 |
| 2. BM25 with titles | exact | 0.759 | 0.653 | 0.183 | 0.664 | 0.610 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.793 | 0.707 | 0.203 | 0.529 | 0.534 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.931** | **0.839** | **0.238** | **0.889** | **0.837** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.776 | 0.714 | 0.056 | 0.444 | 0.488 |
| 2. BM25 with titles | exact | 0.845 | 0.801 | 0.066 | 0.673 | 0.664 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.879 | 0.835 | 0.068 | 0.535 | 0.579 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.966** | **0.925** | **0.074** | **0.892** | **0.871** |

### gmail (55 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.655 | 0.554 | 0.087 | 0.495 | 0.463 |
| 2. BM25 with titles | exact | 0.764 | 0.695 | 0.115 | 0.605 | 0.594 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.782 | 0.697 | 0.109 | 0.656 | 0.621 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.927** | **0.851** | **0.138** | **0.845** | **0.802** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.582 | 0.482 | 0.145 | 0.485 | 0.437 |
| 2. BM25 with titles | exact | 0.727 | 0.626 | 0.189 | 0.599 | 0.563 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.745 | 0.640 | 0.178 | 0.651 | 0.594 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.891** | **0.786** | **0.240** | **0.840** | **0.775** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.782 | 0.693 | 0.053 | 0.504 | 0.501 |
| 2. BM25 with titles | exact | 0.764 | 0.709 | 0.061 | 0.605 | 0.600 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.836 | 0.760 | 0.064 | 0.660 | 0.642 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.927** | **0.857** | **0.071** | **0.845** | **0.805** |

### hubspot (34 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.353 | 0.353 | 0.035 | 0.204 | 0.237 |
| 2. BM25 with titles | exact | 0.706 | 0.706 | 0.074 | 0.509 | 0.555 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.647 | 0.647 | 0.068 | 0.332 | 0.410 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.853** | **0.853** | **0.088** | **0.828** | **0.834** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.235 | 0.235 | 0.047 | 0.188 | 0.199 |
| 2. BM25 with titles | exact | 0.559 | 0.559 | 0.118 | 0.486 | 0.504 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.529 | 0.515 | 0.106 | 0.315 | 0.364 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.824** | **0.824** | **0.171** | **0.824** | **0.824** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.382 | 0.382 | 0.019 | 0.206 | 0.245 |
| 2. BM25 with titles | exact | 0.824 | 0.824 | 0.043 | 0.517 | 0.584 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.794 | 0.794 | 0.041 | 0.342 | 0.447 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.853** | **0.853** | **0.044** | **0.828** | **0.834** |

### fireflies (25 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.400 | 0.345 | 0.072 | 0.235 | 0.260 |
| 2. BM25 with titles | exact | 0.640 | 0.612 | 0.092 | 0.410 | 0.462 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.520 | 0.520 | 0.084 | 0.265 | 0.322 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.760** | **0.725** | **0.112** | **0.520** | **0.565** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.320 | 0.312 | 0.120 | 0.227 | 0.245 |
| 2. BM25 with titles | exact | 0.560 | 0.528 | 0.144 | 0.401 | 0.429 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.480 | 0.456 | 0.136 | 0.258 | 0.294 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.680** | **0.637** | **0.192** | **0.510** | **0.533** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.560 | 0.505 | 0.044 | 0.246 | 0.300 |
| 2. BM25 with titles | exact | 0.640 | 0.620 | 0.048 | 0.410 | 0.466 |
| 3. Hybrid RRF, BM25 with titles | exact | 0.680 | 0.625 | 0.050 | 0.275 | 0.350 |
| 4. Top 100 + rerank-3-lite (v3) | exact | **0.760** | **0.725** | **0.056** | **0.520** | **0.565** |
<!-- end generated -->

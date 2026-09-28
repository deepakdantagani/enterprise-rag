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
| 2026-09-27 | RET-6 | **v2** v1 + `rerank-3-lite` (preview) | 511,957 | 470 | 0.851 | 0.777 | 0.800 | 0.820 | 0.112 | 0.785 | 0.762 | **current version**: v1's top 50 re-sorted by Voyage's cross-encoder; +0.078 recall@10 over v1; interactive report `docs/eval/report.html` |

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

## v0 → v1 → reranking, every step

Generated by `uv run python -m pipeline.eval.results_tables` from `docs/eval/runs` (EVAL-5b):
do not edit between the markers. Steps add one thing each; "exact" searches every vector,
"HNSW" is Qdrant's approximate graph index (BM25 is always exact). Bold = best in its column.

<!-- generated: EVAL-5b -->
### All sources (470 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.687 | 0.626 | 0.088 | 0.508 | 0.508 |
| 1. Dense only | HNSW | 0.660 | 0.599 | 0.084 | 0.486 | 0.486 |
| 2. Sparse only (BM25) | exact | 0.709 | 0.650 | 0.094 | 0.560 | 0.554 |
| 3. Hybrid A (relative) | exact | 0.781 | 0.727 | 0.102 | 0.638 | 0.630 |
| 3. Hybrid A (relative) | HNSW | 0.772 | 0.716 | 0.100 | 0.620 | 0.614 |
| 4. Hybrid RRF (v1) | exact | 0.777 | 0.722 | 0.102 | 0.622 | 0.619 |
| 4. Hybrid RRF | HNSW | 0.762 | 0.706 | 0.099 | 0.598 | 0.596 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.851** | **0.800** | **0.112** | **0.785** | **0.762** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.617 | 0.548 | 0.151 | 0.498 | 0.480 |
| 1. Dense only | HNSW | 0.591 | 0.526 | 0.145 | 0.476 | 0.459 |
| 2. Sparse only (BM25) | exact | 0.664 | 0.587 | 0.159 | 0.555 | 0.529 |
| 3. Hybrid A (relative) | exact | 0.736 | 0.664 | 0.180 | 0.632 | 0.607 |
| 3. Hybrid A (relative) | HNSW | 0.726 | 0.651 | 0.176 | 0.614 | 0.589 |
| 4. Hybrid RRF (v1) | exact | 0.740 | 0.676 | 0.185 | 0.617 | 0.601 |
| 4. Hybrid RRF | HNSW | 0.726 | 0.658 | 0.180 | 0.593 | 0.578 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.843** | **0.777** | **0.210** | **0.784** | **0.751** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.753 | 0.698 | 0.049 | 0.512 | 0.528 |
| 1. Dense only | HNSW | 0.719 | 0.664 | 0.047 | 0.491 | 0.504 |
| 2. Sparse only (BM25) | exact | 0.760 | 0.721 | 0.053 | 0.564 | 0.574 |
| 3. Hybrid A (relative) | exact | 0.828 | 0.784 | 0.057 | 0.641 | 0.647 |
| 3. Hybrid A (relative) | HNSW | 0.819 | 0.774 | 0.056 | 0.623 | 0.631 |
| 4. Hybrid RRF (v1) | exact | 0.836 | 0.791 | 0.057 | 0.626 | 0.638 |
| 4. Hybrid RRF | HNSW | 0.828 | 0.782 | 0.057 | 0.604 | 0.619 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.860** | **0.820** | **0.059** | **0.786** | **0.769** |

### confluence (114 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.772 | 0.572 | 0.144 | 0.591 | 0.493 |
| 1. Dense only | HNSW | 0.737 | 0.534 | 0.136 | 0.561 | 0.464 |
| 2. Sparse only (BM25) | exact | 0.807 | 0.606 | 0.158 | 0.662 | 0.555 |
| 3. Hybrid A (relative) | exact | 0.851 | 0.667 | 0.168 | 0.724 | 0.610 |
| 3. Hybrid A (relative) | HNSW | 0.851 | 0.658 | 0.165 | 0.699 | 0.586 |
| 4. Hybrid RRF (v1) | exact | 0.851 | 0.680 | 0.171 | 0.728 | 0.622 |
| 4. Hybrid RRF | HNSW | 0.842 | 0.665 | 0.166 | 0.699 | 0.596 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.886** | **0.717** | **0.177** | **0.798** | **0.690** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.754 | 0.509 | 0.246 | 0.589 | 0.464 |
| 1. Dense only | HNSW | 0.711 | 0.473 | 0.232 | 0.558 | 0.435 |
| 2. Sparse only (BM25) | exact | 0.772 | 0.514 | 0.240 | 0.657 | 0.509 |
| 3. Hybrid A (relative) | exact | 0.807 | 0.563 | 0.274 | 0.719 | 0.563 |
| 3. Hybrid A (relative) | HNSW | 0.807 | 0.556 | 0.268 | 0.693 | 0.540 |
| 4. Hybrid RRF (v1) | exact | 0.825 | 0.610 | 0.295 | 0.724 | 0.589 |
| 4. Hybrid RRF | HNSW | 0.816 | 0.595 | 0.286 | 0.695 | 0.564 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.886** | **0.678** | **0.316** | **0.798** | **0.668** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.807 | 0.626 | 0.081 | 0.594 | 0.512 |
| 1. Dense only | HNSW | 0.763 | 0.577 | 0.076 | 0.563 | 0.479 |
| 2. Sparse only (BM25) | exact | 0.877 | 0.748 | 0.097 | 0.667 | 0.601 |
| 3. Hybrid A (relative) | exact | 0.877 | 0.738 | 0.097 | 0.726 | 0.635 |
| 3. Hybrid A (relative) | HNSW | 0.877 | 0.735 | 0.096 | 0.701 | 0.614 |
| 4. Hybrid RRF (v1) | exact | 0.886 | 0.746 | 0.098 | 0.731 | 0.646 |
| 4. Hybrid RRF | HNSW | 0.886 | 0.747 | 0.098 | 0.707 | 0.627 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.895** | **0.770** | **0.100** | **0.799** | **0.710** |

### jira (100 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.900 | 0.738 | 0.135 | 0.742 | 0.665 |
| 1. Dense only | HNSW | 0.890 | 0.733 | 0.134 | 0.738 | 0.661 |
| 2. Sparse only (BM25) | exact | 0.860 | 0.724 | 0.145 | 0.749 | 0.672 |
| 3. Hybrid A (relative) | exact | 0.930 | 0.787 | 0.149 | 0.828 | 0.744 |
| 3. Hybrid A (relative) | HNSW | 0.930 | 0.781 | 0.146 | 0.823 | 0.738 |
| 4. Hybrid RRF (v1) | exact | 0.930 | 0.782 | 0.147 | 0.812 | 0.729 |
| 4. Hybrid RRF | HNSW | 0.930 | 0.784 | 0.148 | 0.807 | 0.727 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.960** | **0.823** | **0.162** | **0.898** | **0.808** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.860 | 0.688 | 0.242 | 0.735 | 0.644 |
| 1. Dense only | HNSW | 0.850 | 0.682 | 0.238 | 0.732 | 0.639 |
| 2. Sparse only (BM25) | exact | 0.850 | 0.667 | 0.230 | 0.748 | 0.640 |
| 3. Hybrid A (relative) | exact | 0.920 | 0.735 | 0.256 | 0.827 | 0.718 |
| 3. Hybrid A (relative) | HNSW | 0.920 | 0.733 | 0.254 | 0.822 | 0.714 |
| 4. Hybrid RRF (v1) | exact | 0.920 | 0.754 | 0.266 | 0.811 | 0.714 |
| 4. Hybrid RRF | HNSW | 0.920 | 0.752 | 0.264 | 0.806 | 0.710 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.960** | **0.784** | **0.290** | **0.898** | **0.787** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.910 | 0.766 | 0.073 | 0.742 | 0.676 |
| 1. Dense only | HNSW | 0.900 | 0.760 | 0.072 | 0.739 | 0.672 |
| 2. Sparse only (BM25) | exact | 0.880 | 0.778 | 0.082 | 0.750 | 0.691 |
| 3. Hybrid A (relative) | exact | 0.960 | 0.841 | 0.085 | 0.831 | 0.764 |
| 3. Hybrid A (relative) | HNSW | 0.960 | 0.837 | 0.084 | 0.826 | 0.759 |
| 4. Hybrid RRF (v1) | exact | 0.960 | 0.846 | 0.087 | 0.814 | 0.753 |
| 4. Hybrid RRF | HNSW | 0.960 | 0.848 | 0.087 | 0.809 | 0.751 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.970** | **0.865** | **0.088** | **0.899** | **0.823** |

### slack (79 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.810 | 0.684 | 0.115 | 0.596 | 0.566 |
| 1. Dense only | HNSW | 0.759 | 0.632 | 0.109 | 0.565 | 0.528 |
| 2. Sparse only (BM25) | exact | 0.684 | 0.583 | 0.110 | 0.511 | 0.493 |
| 3. Hybrid A (relative) | exact | 0.835 | 0.731 | 0.124 | 0.678 | 0.633 |
| 3. Hybrid A (relative) | HNSW | 0.810 | 0.704 | 0.120 | 0.656 | 0.609 |
| 4. Hybrid RRF (v1) | exact | 0.823 | 0.721 | 0.124 | 0.652 | 0.615 |
| 4. Hybrid RRF | HNSW | 0.797 | 0.697 | 0.122 | 0.633 | 0.596 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.873** | **0.777** | **0.137** | **0.791** | **0.741** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.709 | 0.587 | 0.200 | 0.581 | 0.529 |
| 1. Dense only | HNSW | 0.684 | 0.560 | 0.192 | 0.554 | 0.501 |
| 2. Sparse only (BM25) | exact | 0.620 | 0.497 | 0.170 | 0.502 | 0.457 |
| 3. Hybrid A (relative) | exact | 0.797 | 0.673 | 0.218 | 0.673 | 0.609 |
| 3. Hybrid A (relative) | HNSW | 0.772 | 0.647 | 0.213 | 0.651 | 0.586 |
| 4. Hybrid RRF (v1) | exact | 0.810 | 0.699 | 0.233 | 0.651 | 0.605 |
| 4. Hybrid RRF | HNSW | 0.785 | 0.676 | 0.230 | 0.632 | 0.587 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.861** | **0.744** | **0.253** | **0.789** | **0.726** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.848 | 0.737 | 0.063 | 0.599 | 0.582 |
| 1. Dense only | HNSW | 0.797 | 0.685 | 0.060 | 0.568 | 0.545 |
| 2. Sparse only (BM25) | exact | 0.709 | 0.643 | 0.063 | 0.513 | 0.513 |
| 3. Hybrid A (relative) | exact | **0.886** | 0.790 | 0.070 | 0.681 | 0.652 |
| 3. Hybrid A (relative) | HNSW | 0.848 | 0.753 | 0.068 | 0.658 | 0.625 |
| 4. Hybrid RRF (v1) | exact | **0.886** | 0.792 | 0.071 | 0.657 | 0.638 |
| 4. Hybrid RRF | HNSW | 0.861 | 0.769 | 0.070 | 0.638 | 0.618 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.886** | **0.806** | **0.074** | **0.792** | **0.752** |

### github (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.800 | 0.673 | 0.127 | 0.624 | 0.574 |
| 1. Dense only | HNSW | 0.783 | 0.659 | 0.127 | 0.622 | 0.570 |
| 2. Sparse only (BM25) | exact | 0.750 | 0.617 | 0.130 | 0.549 | 0.502 |
| 3. Hybrid A (relative) | exact | 0.833 | 0.716 | 0.140 | 0.694 | 0.645 |
| 3. Hybrid A (relative) | HNSW | 0.833 | 0.716 | 0.140 | 0.684 | 0.638 |
| 4. Hybrid RRF (v1) | exact | 0.833 | 0.717 | 0.137 | 0.688 | 0.641 |
| 4. Hybrid RRF | HNSW | 0.817 | 0.698 | 0.133 | 0.671 | 0.624 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.900** | **0.781** | **0.143** | **0.856** | **0.768** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.717 | 0.570 | 0.217 | 0.614 | 0.537 |
| 1. Dense only | HNSW | 0.717 | 0.570 | 0.217 | 0.614 | 0.537 |
| 2. Sparse only (BM25) | exact | 0.700 | 0.521 | 0.187 | 0.544 | 0.457 |
| 3. Hybrid A (relative) | exact | 0.783 | 0.622 | 0.230 | 0.686 | 0.605 |
| 3. Hybrid A (relative) | HNSW | 0.783 | 0.622 | 0.230 | 0.678 | 0.599 |
| 4. Hybrid RRF (v1) | exact | 0.817 | 0.683 | 0.240 | 0.686 | 0.622 |
| 4. Hybrid RRF | HNSW | 0.800 | 0.666 | 0.237 | 0.669 | 0.605 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.883** | **0.719** | **0.247** | **0.853** | **0.740** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.850 | 0.743 | 0.072 | 0.627 | 0.595 |
| 1. Dense only | HNSW | 0.833 | 0.727 | 0.071 | 0.625 | 0.590 |
| 2. Sparse only (BM25) | exact | 0.817 | 0.706 | 0.074 | 0.553 | 0.528 |
| 3. Hybrid A (relative) | exact | 0.867 | 0.770 | **0.079** | 0.696 | 0.664 |
| 3. Hybrid A (relative) | HNSW | 0.850 | 0.751 | 0.077 | 0.685 | 0.652 |
| 4. Hybrid RRF (v1) | exact | 0.867 | 0.770 | **0.079** | 0.691 | 0.662 |
| 4. Hybrid RRF | HNSW | 0.850 | 0.754 | 0.078 | 0.674 | 0.645 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.900** | **0.801** | 0.078 | **0.856** | **0.778** |

### google_drive (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.700 | 0.585 | 0.102 | 0.519 | 0.490 |
| 1. Dense only | HNSW | 0.667 | 0.539 | 0.088 | 0.483 | 0.448 |
| 2. Sparse only (BM25) | exact | 0.683 | 0.603 | 0.112 | 0.579 | 0.540 |
| 3. Hybrid A (relative) | exact | 0.767 | 0.691 | 0.120 | 0.629 | 0.601 |
| 3. Hybrid A (relative) | HNSW | 0.767 | 0.681 | 0.117 | 0.615 | 0.584 |
| 4. Hybrid RRF (v1) | exact | 0.767 | 0.666 | 0.117 | 0.602 | 0.566 |
| 4. Hybrid RRF | HNSW | 0.767 | 0.653 | 0.108 | 0.583 | 0.541 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.817** | **0.748** | **0.132** | **0.744** | **0.716** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.617 | 0.496 | 0.170 | 0.507 | 0.457 |
| 1. Dense only | HNSW | 0.567 | 0.456 | 0.150 | 0.469 | 0.418 |
| 2. Sparse only (BM25) | exact | 0.667 | 0.555 | 0.183 | 0.577 | 0.517 |
| 3. Hybrid A (relative) | exact | 0.733 | 0.624 | 0.200 | 0.626 | 0.572 |
| 3. Hybrid A (relative) | HNSW | 0.733 | 0.615 | 0.197 | 0.612 | 0.556 |
| 4. Hybrid RRF (v1) | exact | 0.700 | 0.578 | 0.193 | 0.593 | 0.530 |
| 4. Hybrid RRF | HNSW | 0.717 | 0.572 | 0.187 | 0.577 | 0.510 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.817** | **0.728** | **0.243** | **0.744** | **0.705** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.733 | 0.634 | 0.057 | 0.522 | 0.505 |
| 1. Dense only | HNSW | 0.700 | 0.587 | 0.050 | 0.485 | 0.464 |
| 2. Sparse only (BM25) | exact | 0.700 | 0.648 | 0.062 | 0.580 | 0.554 |
| 3. Hybrid A (relative) | exact | **0.833** | **0.763** | 0.069 | 0.634 | 0.623 |
| 3. Hybrid A (relative) | HNSW | **0.833** | 0.760 | 0.068 | 0.620 | 0.609 |
| 4. Hybrid RRF (v1) | exact | **0.833** | 0.760 | 0.068 | 0.607 | 0.594 |
| 4. Hybrid RRF | HNSW | **0.833** | 0.760 | 0.068 | 0.588 | 0.575 |
| 5. v1 + rerank-3-lite (v2) | exact | 0.817 | **0.763** | **0.070** | **0.744** | **0.722** |

### linear (58 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.655 | 0.593 | 0.093 | 0.436 | 0.456 |
| 1. Dense only | HNSW | 0.672 | 0.611 | 0.095 | 0.426 | 0.452 |
| 2. Sparse only (BM25) | exact | 0.793 | 0.706 | 0.110 | 0.636 | 0.612 |
| 3. Hybrid A (relative) | exact | 0.828 | 0.754 | 0.117 | 0.650 | 0.631 |
| 3. Hybrid A (relative) | HNSW | 0.828 | 0.754 | 0.117 | 0.650 | 0.631 |
| 4. Hybrid RRF (v1) | exact | 0.828 | 0.756 | 0.119 | 0.657 | 0.642 |
| 4. Hybrid RRF | HNSW | 0.828 | 0.755 | 0.117 | 0.655 | 0.638 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.897** | **0.826** | **0.122** | **0.828** | **0.800** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.603 | 0.526 | 0.159 | 0.429 | 0.430 |
| 1. Dense only | HNSW | 0.603 | 0.526 | 0.159 | 0.417 | 0.421 |
| 2. Sparse only (BM25) | exact | 0.759 | 0.648 | 0.186 | 0.630 | 0.587 |
| 3. Hybrid A (relative) | exact | 0.793 | 0.683 | 0.197 | 0.647 | 0.603 |
| 3. Hybrid A (relative) | HNSW | 0.793 | 0.683 | 0.197 | 0.647 | 0.602 |
| 4. Hybrid RRF (v1) | exact | 0.776 | 0.674 | 0.200 | 0.649 | 0.608 |
| 4. Hybrid RRF | HNSW | 0.759 | 0.665 | 0.200 | 0.645 | 0.604 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.879** | **0.782** | **0.221** | **0.825** | **0.781** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.776 | 0.714 | 0.056 | 0.444 | 0.488 |
| 1. Dense only | HNSW | 0.776 | 0.714 | 0.056 | 0.433 | 0.481 |
| 2. Sparse only (BM25) | exact | 0.828 | 0.768 | 0.064 | 0.638 | 0.632 |
| 3. Hybrid A (relative) | exact | 0.862 | 0.812 | 0.067 | 0.653 | 0.651 |
| 3. Hybrid A (relative) | HNSW | 0.862 | 0.812 | 0.067 | 0.653 | 0.650 |
| 4. Hybrid RRF (v1) | exact | 0.879 | 0.829 | 0.068 | 0.661 | 0.664 |
| 4. Hybrid RRF | HNSW | 0.879 | 0.829 | 0.068 | 0.658 | 0.662 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.914** | **0.863** | **0.070** | **0.830** | **0.815** |

### gmail (55 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.655 | 0.554 | 0.087 | 0.495 | 0.463 |
| 1. Dense only | HNSW | 0.600 | 0.500 | 0.082 | 0.456 | 0.421 |
| 2. Sparse only (BM25) | exact | 0.745 | 0.672 | 0.111 | 0.606 | 0.593 |
| 3. Hybrid A (relative) | exact | 0.782 | 0.694 | 0.107 | 0.675 | 0.643 |
| 3. Hybrid A (relative) | HNSW | 0.764 | 0.672 | 0.104 | 0.642 | 0.611 |
| 4. Hybrid RRF (v1) | exact | 0.782 | 0.696 | 0.107 | 0.656 | 0.632 |
| 4. Hybrid RRF | HNSW | 0.745 | 0.660 | 0.104 | 0.616 | 0.592 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.873** | **0.791** | **0.129** | **0.774** | **0.737** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.582 | 0.482 | 0.145 | 0.485 | 0.437 |
| 1. Dense only | HNSW | 0.545 | 0.446 | 0.138 | 0.449 | 0.401 |
| 2. Sparse only (BM25) | exact | 0.691 | 0.607 | 0.182 | 0.599 | 0.565 |
| 3. Hybrid A (relative) | exact | 0.782 | 0.675 | 0.196 | 0.675 | 0.633 |
| 3. Hybrid A (relative) | HNSW | 0.745 | 0.638 | 0.189 | 0.638 | 0.596 |
| 4. Hybrid RRF (v1) | exact | 0.764 | 0.683 | 0.204 | 0.653 | 0.625 |
| 4. Hybrid RRF | HNSW | 0.727 | 0.642 | 0.193 | 0.614 | 0.583 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.855** | **0.750** | **0.233** | **0.771** | **0.718** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.782 | 0.693 | 0.053 | 0.504 | 0.501 |
| 1. Dense only | HNSW | 0.745 | 0.656 | 0.051 | 0.467 | 0.464 |
| 2. Sparse only (BM25) | exact | 0.764 | 0.704 | 0.059 | 0.607 | 0.603 |
| 3. Hybrid A (relative) | exact | 0.818 | 0.731 | 0.059 | 0.678 | 0.656 |
| 3. Hybrid A (relative) | HNSW | 0.818 | 0.731 | 0.059 | 0.645 | 0.630 |
| 4. Hybrid RRF (v1) | exact | 0.836 | 0.751 | 0.061 | 0.659 | 0.649 |
| 4. Hybrid RRF | HNSW | 0.818 | 0.732 | 0.060 | 0.622 | 0.614 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.873** | **0.802** | **0.066** | **0.774** | **0.741** |

### hubspot (34 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.353 | 0.353 | 0.035 | 0.204 | 0.237 |
| 1. Dense only | HNSW | 0.353 | 0.353 | 0.035 | 0.204 | 0.237 |
| 2. Sparse only (BM25) | exact | 0.588 | 0.574 | 0.059 | 0.375 | 0.414 |
| 3. Hybrid A (relative) | exact | 0.559 | 0.544 | 0.056 | 0.361 | 0.403 |
| 3. Hybrid A (relative) | HNSW | 0.559 | 0.544 | 0.056 | 0.370 | 0.409 |
| 4. Hybrid RRF (v1) | exact | 0.529 | 0.515 | 0.053 | 0.288 | 0.341 |
| 4. Hybrid RRF | HNSW | 0.529 | 0.515 | 0.053 | 0.293 | 0.345 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.765** | **0.765** | **0.079** | **0.743** | **0.744** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.235 | 0.235 | 0.047 | 0.188 | 0.199 |
| 1. Dense only | HNSW | 0.235 | 0.235 | 0.047 | 0.188 | 0.199 |
| 2. Sparse only (BM25) | exact | 0.529 | 0.515 | 0.106 | 0.368 | 0.396 |
| 3. Hybrid A (relative) | exact | 0.471 | 0.456 | 0.094 | 0.348 | 0.374 |
| 3. Hybrid A (relative) | HNSW | 0.471 | 0.456 | 0.094 | 0.358 | 0.380 |
| 4. Hybrid RRF (v1) | exact | 0.412 | 0.412 | 0.082 | 0.271 | 0.305 |
| 4. Hybrid RRF | HNSW | 0.441 | 0.426 | 0.088 | 0.281 | 0.316 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.765** | **0.765** | **0.159** | **0.743** | **0.744** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.382 | 0.382 | 0.019 | 0.206 | 0.245 |
| 1. Dense only | HNSW | 0.382 | 0.382 | 0.019 | 0.206 | 0.245 |
| 2. Sparse only (BM25) | exact | 0.706 | 0.706 | 0.037 | 0.383 | 0.448 |
| 3. Hybrid A (relative) | exact | 0.676 | 0.662 | 0.034 | 0.370 | 0.435 |
| 3. Hybrid A (relative) | HNSW | 0.676 | 0.662 | 0.034 | 0.380 | 0.441 |
| 4. Hybrid RRF (v1) | exact | 0.676 | 0.662 | 0.034 | 0.298 | 0.378 |
| 4. Hybrid RRF | HNSW | 0.676 | 0.662 | 0.034 | 0.304 | 0.382 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.765** | **0.765** | **0.040** | **0.743** | **0.744** |

### fireflies (25 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.400 | 0.345 | 0.072 | 0.235 | 0.260 |
| 1. Dense only | HNSW | 0.400 | 0.345 | 0.072 | 0.219 | 0.246 |
| 2. Sparse only (BM25) | exact | 0.640 | 0.620 | 0.096 | 0.364 | 0.426 |
| 3. Hybrid A (relative) | exact | 0.600 | 0.580 | 0.092 | 0.352 | 0.403 |
| 3. Hybrid A (relative) | HNSW | 0.560 | 0.540 | 0.088 | 0.322 | 0.371 |
| 4. Hybrid RRF (v1) | exact | 0.560 | 0.540 | 0.088 | 0.373 | 0.407 |
| 4. Hybrid RRF | HNSW | 0.520 | 0.500 | 0.084 | 0.287 | 0.331 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.680** | **0.645** | **0.100** | **0.520** | **0.542** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.320 | 0.312 | 0.120 | 0.227 | 0.245 |
| 1. Dense only | HNSW | 0.280 | 0.272 | 0.112 | 0.207 | 0.219 |
| 2. Sparse only (BM25) | exact | 0.440 | 0.416 | 0.128 | 0.340 | 0.355 |
| 3. Hybrid A (relative) | exact | 0.480 | 0.464 | 0.144 | 0.337 | 0.360 |
| 3. Hybrid A (relative) | HNSW | 0.440 | 0.424 | 0.136 | 0.307 | 0.328 |
| 4. Hybrid RRF (v1) | exact | 0.480 | 0.444 | 0.144 | 0.363 | 0.373 |
| 4. Hybrid RRF | HNSW | 0.440 | 0.404 | 0.136 | 0.277 | 0.297 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.680** | **0.637** | **0.192** | **0.520** | **0.537** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.560 | 0.505 | 0.044 | 0.246 | 0.300 |
| 1. Dense only | HNSW | 0.480 | 0.425 | 0.040 | 0.245 | 0.281 |
| 2. Sparse only (BM25) | exact | 0.640 | 0.620 | 0.048 | 0.364 | 0.426 |
| 3. Hybrid A (relative) | exact | 0.640 | 0.620 | 0.048 | 0.354 | 0.412 |
| 3. Hybrid A (relative) | HNSW | 0.640 | 0.620 | 0.048 | 0.328 | 0.392 |
| 4. Hybrid RRF (v1) | exact | 0.680 | 0.625 | 0.050 | 0.380 | 0.428 |
| 4. Hybrid RRF | HNSW | 0.680 | 0.625 | 0.050 | 0.296 | 0.362 |
| 5. v1 + rerank-3-lite (v2) | exact | **0.720** | **0.665** | **0.052** | **0.523** | **0.548** |
<!-- end generated -->

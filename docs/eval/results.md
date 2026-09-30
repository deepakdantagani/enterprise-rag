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
| 2026-09-27 | EVAL-3i, RET-8 | **v3** dense + BM25 with titles, RRF over 200-deep lists, top 100 + `rerank-3-lite` | 511,957 | 470 | 0.891 | 0.813 | **0.845** | 0.863 | 0.118 | 0.818 | 0.799 | **current version**: +0.045 recall@10 over v2; the top 100 without titles scores 0.832, with them 0.845 (+0.013, 95% CI +0.002..+0.025); HubSpot 0.765 → 0.853; dense vectors still without titles |
| 2026-09-28 | EVAL-3k, EVAL-3l | **v4** v3 with dense on `voyage-4-lite` with titles, `titles__voyage_4_lite__bm25` | 511,957 | 470 | 0.879 | 0.803 | **0.834** | 0.846 | 0.116 | 0.809 | 0.790 | **current version, the base**: −0.011 recall@10 against v3 (95% CI −0.024..+0.001, within noise) at a third of the embedding cost (~$12 against ~$35 for the corpus); dense and BM25 index the same titled chunks; interactive report `docs/eval/report.html` |

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

## The v4 chain, every step

Generated by `uv run python -m pipeline.eval.results_tables` from `docs/eval/runs` (EVAL-5b):
do not edit between the markers. Steps add one thing each, all searched exactly, on the v4
collection (dense voyage-4-lite + BM25 over the same chunks). Earlier chains stay in
`docs/eval/runs` and the rows above. Bold = best in its column.

<!-- generated: EVAL-5b -->
### All sources (470 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.666 | 0.606 | 0.086 | 0.483 | 0.487 |
| 2. Sparse only (BM25) | exact | 0.740 | 0.688 | 0.099 | 0.590 | 0.586 |
| 3. Hybrid RRF | exact | 0.785 | 0.732 | 0.104 | 0.612 | 0.615 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.879** | **0.834** | **0.116** | **0.809** | **0.790** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.615 | 0.538 | 0.149 | 0.476 | 0.462 |
| 2. Sparse only (BM25) | exact | 0.685 | 0.610 | 0.166 | 0.582 | 0.556 |
| 3. Hybrid RRF | exact | 0.745 | 0.671 | 0.183 | 0.607 | 0.591 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.864** | **0.803** | **0.216** | **0.807** | **0.777** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.719 | 0.671 | 0.048 | 0.487 | 0.505 |
| 2. Sparse only (BM25) | exact | 0.772 | 0.739 | 0.055 | 0.592 | 0.601 |
| 3. Hybrid RRF | exact | 0.840 | 0.801 | 0.058 | 0.616 | 0.634 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.881** | **0.846** | **0.061** | **0.809** | **0.795** |

### confluence (114 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.772 | 0.565 | 0.144 | 0.579 | 0.491 |
| 2. Sparse only (BM25) | exact | 0.851 | 0.670 | 0.171 | 0.688 | 0.590 |
| 3. Hybrid RRF | exact | 0.860 | 0.680 | 0.173 | 0.724 | 0.626 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.912** | **0.762** | **0.188** | **0.804** | **0.716** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.746 | 0.480 | 0.233 | 0.575 | 0.452 |
| 2. Sparse only (BM25) | exact | 0.781 | 0.528 | 0.253 | 0.679 | 0.527 |
| 3. Hybrid RRF | exact | 0.833 | 0.588 | 0.281 | 0.721 | 0.583 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.904** | **0.708** | **0.330** | **0.803** | **0.689** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.798 | 0.635 | 0.083 | 0.580 | 0.515 |
| 2. Sparse only (BM25) | exact | 0.886 | 0.771 | 0.101 | 0.691 | 0.625 |
| 3. Hybrid RRF | exact | 0.895 | 0.761 | 0.100 | 0.726 | 0.655 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.912** | **0.793** | **0.103** | **0.804** | **0.730** |

### jira (100 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.890 | 0.724 | 0.133 | 0.703 | 0.639 |
| 2. Sparse only (BM25) | exact | 0.870 | 0.732 | 0.145 | 0.764 | 0.682 |
| 3. Hybrid RRF | exact | 0.940 | 0.788 | 0.150 | 0.805 | 0.726 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.970** | **0.845** | **0.167** | **0.907** | **0.820** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.840 | 0.645 | 0.230 | 0.696 | 0.609 |
| 2. Sparse only (BM25) | exact | 0.860 | 0.670 | 0.234 | 0.763 | 0.650 |
| 3. Hybrid RRF | exact | 0.930 | 0.747 | 0.260 | 0.803 | 0.704 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.970** | **0.798** | **0.294** | **0.907** | **0.796** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.930 | 0.792 | 0.075 | 0.706 | 0.661 |
| 2. Sparse only (BM25) | exact | 0.880 | 0.789 | 0.083 | 0.765 | 0.704 |
| 3. Hybrid RRF | exact | **0.970** | 0.853 | 0.087 | 0.807 | 0.749 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.970** | **0.874** | **0.091** | **0.907** | **0.832** |

### slack (79 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.785 | 0.661 | 0.113 | 0.561 | 0.539 |
| 2. Sparse only (BM25) | exact | 0.684 | 0.590 | 0.111 | 0.535 | 0.506 |
| 3. Hybrid RRF | exact | 0.835 | 0.727 | 0.128 | 0.639 | 0.608 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.873** | **0.778** | **0.137** | **0.795** | **0.742** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.759 | 0.620 | 0.205 | 0.557 | 0.522 |
| 2. Sparse only (BM25) | exact | 0.646 | 0.510 | 0.175 | 0.530 | 0.472 |
| 3. Hybrid RRF | exact | 0.797 | 0.681 | 0.225 | 0.634 | 0.588 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.861** | **0.739** | **0.248** | **0.793** | **0.724** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.835 | 0.727 | 0.063 | 0.564 | 0.558 |
| 2. Sparse only (BM25) | exact | 0.696 | 0.638 | 0.065 | 0.536 | 0.524 |
| 3. Hybrid RRF | exact | 0.861 | 0.776 | 0.072 | 0.640 | 0.625 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.886** | **0.808** | **0.075** | **0.796** | **0.754** |

### github (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.767 | 0.637 | 0.122 | 0.587 | 0.547 |
| 2. Sparse only (BM25) | exact | 0.767 | 0.623 | 0.128 | 0.576 | 0.517 |
| 3. Hybrid RRF | exact | 0.817 | 0.697 | 0.138 | 0.668 | 0.617 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.883** | **0.764** | **0.142** | **0.845** | **0.761** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.717 | 0.564 | 0.210 | 0.580 | 0.517 |
| 2. Sparse only (BM25) | exact | 0.700 | 0.507 | 0.187 | 0.567 | 0.466 |
| 3. Hybrid RRF | exact | 0.783 | 0.639 | 0.230 | 0.664 | 0.589 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.883** | **0.726** | **0.253** | **0.845** | **0.741** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.767 | 0.672 | 0.070 | 0.587 | 0.561 |
| 2. Sparse only (BM25) | exact | 0.800 | 0.700 | 0.075 | 0.579 | 0.543 |
| 3. Hybrid RRF | exact | 0.850 | 0.749 | 0.077 | 0.671 | 0.634 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.883** | **0.786** | **0.078** | **0.845** | **0.771** |

### google_drive (60 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.633 | 0.527 | 0.100 | 0.478 | 0.448 |
| 2. Sparse only (BM25) | exact | 0.733 | 0.666 | 0.118 | 0.621 | 0.589 |
| 3. Hybrid RRF | exact | 0.750 | 0.673 | 0.122 | 0.620 | 0.581 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.867** | **0.786** | **0.130** | **0.787** | **0.751** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.617 | 0.477 | 0.167 | 0.476 | 0.425 |
| 2. Sparse only (BM25) | exact | 0.717 | 0.612 | 0.197 | 0.619 | 0.564 |
| 3. Hybrid RRF | exact | 0.717 | 0.594 | 0.203 | 0.615 | 0.548 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.867** | **0.775** | **0.247** | **0.787** | **0.745** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.667 | 0.567 | 0.054 | 0.481 | 0.460 |
| 2. Sparse only (BM25) | exact | 0.733 | 0.687 | 0.065 | 0.621 | 0.598 |
| 3. Hybrid RRF | exact | 0.817 | 0.763 | 0.070 | 0.625 | 0.608 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.867** | **0.810** | **0.072** | **0.787** | **0.762** |

### linear (58 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.638 | 0.568 | 0.090 | 0.384 | 0.421 |
| 2. Sparse only (BM25) | exact | 0.793 | 0.722 | 0.112 | 0.669 | 0.640 |
| 3. Hybrid RRF | exact | 0.845 | 0.774 | 0.121 | 0.643 | 0.640 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.914** | **0.852** | **0.126** | **0.856** | **0.821** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.603 | 0.518 | 0.155 | 0.379 | 0.402 |
| 2. Sparse only (BM25) | exact | 0.759 | 0.653 | 0.183 | 0.664 | 0.610 |
| 3. Hybrid RRF | exact | 0.776 | 0.666 | 0.193 | 0.633 | 0.597 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.897** | **0.804** | **0.231** | **0.854** | **0.803** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.672 | 0.624 | 0.053 | 0.386 | 0.438 |
| 2. Sparse only (BM25) | exact | 0.845 | 0.801 | 0.066 | 0.673 | 0.664 |
| 3. Hybrid RRF | exact | 0.879 | 0.835 | 0.068 | 0.646 | 0.660 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.914** | **0.873** | **0.072** | **0.856** | **0.832** |

### gmail (55 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.655 | 0.563 | 0.091 | 0.486 | 0.469 |
| 2. Sparse only (BM25) | exact | 0.764 | 0.695 | 0.115 | 0.605 | 0.594 |
| 3. Hybrid RRF | exact | 0.818 | 0.728 | 0.116 | 0.605 | 0.602 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.927** | **0.848** | **0.136** | **0.845** | **0.799** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.600 | 0.491 | 0.153 | 0.478 | 0.441 |
| 2. Sparse only (BM25) | exact | 0.727 | 0.626 | 0.189 | 0.599 | 0.563 |
| 3. Hybrid RRF | exact | 0.764 | 0.670 | 0.204 | 0.598 | 0.578 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.891** | **0.782** | **0.240** | **0.840** | **0.772** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.727 | 0.640 | 0.051 | 0.491 | 0.489 |
| 2. Sparse only (BM25) | exact | 0.764 | 0.709 | 0.061 | 0.605 | 0.600 |
| 3. Hybrid RRF | exact | 0.836 | 0.763 | 0.065 | 0.606 | 0.614 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.927** | **0.857** | **0.071** | **0.845** | **0.804** |

### hubspot (34 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.324 | 0.309 | 0.032 | 0.165 | 0.191 |
| 2. Sparse only (BM25) | exact | 0.706 | 0.706 | 0.074 | 0.509 | 0.555 |
| 3. Hybrid RRF | exact | 0.647 | 0.647 | 0.068 | 0.361 | 0.424 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.853** | **0.853** | **0.088** | **0.829** | **0.835** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.265 | 0.250 | 0.053 | 0.158 | 0.172 |
| 2. Sparse only (BM25) | exact | 0.559 | 0.559 | 0.118 | 0.486 | 0.504 |
| 3. Hybrid RRF | exact | 0.529 | 0.515 | 0.106 | 0.344 | 0.380 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.853** | **0.853** | **0.176** | **0.829** | **0.835** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.441 | 0.426 | 0.022 | 0.173 | 0.220 |
| 2. Sparse only (BM25) | exact | 0.824 | 0.824 | 0.043 | 0.517 | 0.584 |
| 3. Hybrid RRF | exact | 0.794 | 0.794 | 0.041 | 0.370 | 0.461 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.853** | **0.853** | **0.044** | **0.829** | **0.835** |

### fireflies (25 questions)

#### k = 10

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.440 | 0.440 | 0.076 | 0.261 | 0.300 |
| 2. Sparse only (BM25) | exact | 0.640 | 0.612 | 0.092 | 0.410 | 0.462 |
| 3. Hybrid RRF | exact | 0.560 | 0.540 | 0.088 | 0.363 | 0.399 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.720** | **0.720** | **0.108** | **0.520** | **0.569** |

#### k = 5

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.320 | 0.312 | 0.120 | 0.243 | 0.256 |
| 2. Sparse only (BM25) | exact | 0.560 | 0.528 | 0.144 | 0.401 | 0.429 |
| 3. Hybrid RRF | exact | 0.520 | 0.476 | 0.144 | 0.357 | 0.371 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.600** | **0.592** | **0.176** | **0.507** | **0.525** |

#### k = 20

| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |
|---|---|---|---|---|---|---|
| 1. Dense only | exact | 0.520 | 0.520 | 0.042 | 0.267 | 0.322 |
| 2. Sparse only (BM25) | exact | 0.640 | 0.620 | 0.048 | 0.410 | 0.466 |
| 3. Hybrid RRF | exact | 0.680 | 0.660 | 0.050 | 0.371 | 0.429 |
| 4. Top 100 + rerank-3-lite (v4) | exact | **0.720** | **0.720** | **0.054** | **0.520** | **0.569** |
<!-- end generated -->

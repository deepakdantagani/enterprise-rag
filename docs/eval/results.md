# Retrieval results

One row per run of `python -m pipeline.eval.baseline` (or a later variant). Every clean-up story
adds its row and must beat the baseline, or say why not. Metrics are LlamaIndex's, on the first
k distinct documents (EVAL-1), averaged over the questions that have expected documents.
Each run's full table (per question type, per source, k = 5, 10, 20) is in
`runs/<date>-<collection>/metrics.json` (gitignored; re-run the command to get it back).

| date | code | run | documents | questions | recall@5 | recall@10 | recall@20 | mrr@10 | ndcg@10 | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-26 | EVAL-3d3 | `baseline_sample` | 207 | 27 | 0.889 | 0.963 | 0.963 | 0.854 | 0.880 | wiring check only: 207-document haystack, all `basic`; not the baseline |

# enterprise-rag

A retrieval-augmented question-answering system over a **512K-document enterprise corpus**
(Slack, Gmail, Jira, Linear, Confluence, GitHub, Google Drive, HubSpot, meeting transcripts),
built on **LlamaIndex + Qdrant + Voyage AI**, and measured against the public
[EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench) leaderboard.

**Goal:** a top-5 place on the leaderboard ([PROJECT_GOAL.md](PROJECT_GOAL.md)).

## Results so far

Retrieval is scored with LlamaIndex's `RetrieverEvaluator` on the 470 benchmark questions that
have gold documents. Each version changes one thing, and every row is reproducible from saved
runs in [`docs/eval/`](docs/eval/results.md).

| version | what changed | recall@10 | MRR@10 |
|---|---|---|---|
| v0 | naive baseline: dense `voyage-4` only, library defaults | 0.609 | 0.493 |
| v1 | + BM25 keyword search, fused with dense by reciprocal rank fusion | 0.722 | 0.622 |
| v2 | + Voyage `rerank-3-lite` cross-encoder over the top 50 | 0.800 | 0.785 |
| v3 | + document titles in the indexed text, a 200-deep fusion pool, the top 100 reranked | **0.845** | 0.818 |
| v4 | dense vectors on `voyage-4-lite`: **one third of the embedding cost**, within noise of v3 | 0.834 | 0.809 |

**+37% recall@10 over the baseline.** v4 is the production base. It was chosen on cost, and the
difference from v3 was checked with a paired 95% confidence interval, not on the point estimate
alone.

**Answer generation (in progress).** v4's top 10 whole documents go to a local `gemma4:26b`
(Ollama, $0 per answer) with a prompt whose rules come from the benchmark's own judge prompts.
All 500 benchmark questions have been answered. The leaderboard score comes next: the mean over
500 questions of correct (0/1) × completeness (%), judged by an LLM. For reference, the BM25 +
GPT-5.4 baseline scores 50.6, and 10th place is 65.61.

## Architecture

```
                     ┌──────────── ingestion (offline) ─────────────┐
 documents.parquet → │ per-source cleaning → titled chunks          │
 511,962 docs        │ SentenceSplitter(512) → voyage-4-lite        │
                     │ + FastEmbed BM25  →  Qdrant (dense + sparse) │
                     └──────────────────────────────────────────────┘
                                         │
 question ─→ QueryFusionRetriever: dense top 200 + BM25 top 200, RRF → top 100 chunks
          ─→ VoyageAIRerank (rerank-3-lite) → chunks re-sorted
          ─→ FullDocuments postprocessor: first 10 distinct documents, read whole
          ─→ RetrieverQueryEngine + answer prompt → gemma4:26b → answer + document ids
```

Everything in the query path is a LlamaIndex component (`QueryFusionRetriever`,
`VoyageAIRerank`, `RetrieverQueryEngine`, `PromptTemplate`). Custom logic enters only as a
`BaseNodePostprocessor` or `NodeParser` subclass
([`pipeline/eval/answers.py`](pipeline/eval/answers.py)).

**Ask page.** A Gradio UI ([`pipeline/eval/ask_page.py`](pipeline/eval/ask_page.py)) answers any
question live and streams the answer with its 10 source cards. For a benchmark question it also
shows the gold answer and facts next to ours. Every request is traced in **Arize Phoenix**
through OpenInference.

## Engineering practice

- **Measured, not guessed.** Every design decision cites a count from the real corpus. Examples:
  4 document ids that name two different documents, and a 1.4 GB single-row-group parquet that
  makes every read cost 1.2 s. The decisions are in [`docs/decisions/`](docs/decisions/) and
  [`docs/design/`](docs/design/).
- **Story-driven, test-first.** 107 user stories ([`docs/stories.md`](docs/stories.md)), each one
  function and one small PR, written red-tests-first. There are about 700 unit tests plus
  doctests, and real-data tests pin the measured numbers.
- **Byte-exact goldens.** Each cleaned corpus has a sha256 fingerprint, so a refactor must leave
  every output byte unchanged.
- **Cost discipline.** Question embeddings and reranks are saved once and replayed, so re-scoring
  costs $0. Every paid run is estimated before it starts, and the full corpus embedding costs
  about $12 on `voyage-4-lite`.
- **Resumable long runs.** Embedding (1.6M chunks) and answering (500 × ~40 s) write each result
  as soon as it is made. A crash resumes without redoing any finished work.
- **Observability.** LlamaIndex instrumentation events go to a JSON-lines run log for each stage,
  and Phoenix records traces for retrieval and answering.
- **Per-source pipelines.** Slack, Gmail, and Confluence each have their own cleaning pipeline
  (unescaping, quote stripping, speaker parsing, and heading detection with markdown-it).
  Confluence headings and Slack message starts are checked against hand-labelled truth sets.

## Layout

```
pipeline/
  eval/         retrieval, reranking, answer generation, scoring, ask page, reports
  slack/        Slack threads → clean text → one node per thread
  gmail/        Gmail threads → messages, headers, quotes, attachments
  *.py          Confluence: cleaning, heading detection, markdown with stable line ranges
tests/          unittest suite, doctests, goldens, hand-labelled truth sets
docs/
  stories/      every story with acceptance criteria and measured numbers
  eval/         results table, per-run metrics, interactive report (report.html)
  design/       system design per source
  decisions/    one record per decision: why, evidence, rejected options
```

## Run

```sh
uv sync                                                  # pinned dependencies
uv run python -m unittest discover tests                 # full suite (real-data tests skip without data/)
uv run python -m pipeline.eval.ask_page                  # ask page on :7860 (needs Qdrant, Ollama, VOYAGE_API_KEY)
uv run python -m pipeline.eval.answer_run                # answer all 500 benchmark questions (resumable)
```

The data is the benchmark's corpus
([Hugging Face](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench), MIT), kept in
`data/` (gitignored). API keys live only in `.env`.

## Stack

Python 3.14 · LlamaIndex · Qdrant · Voyage AI (`voyage-4`, `voyage-4-lite`, `rerank-3-lite`) ·
FastEmbed BM25 · Ollama (`gemma4:26b`) · Gradio · Arize Phoenix / OpenInference · pyarrow · uv

# Eval stories

How we score retrieval on EnterpriseRAG-Bench, across every source. Rules and template:
[stories.md](../stories.md).

Why this comes first: the plan is a naive baseline (every document, `SentenceSplitter(512)`,
a local embedder, no cleaning) and then one clean-up story at a time. A clean-up story is
only worth merging if it moves a number, so the number has to exist before the baseline.

LlamaIndex first: the scoring is LlamaIndex's `RetrieverEvaluator` and its metrics
(`hit_rate`, `recall`, `mrr`, `ndcg`). Our code is only what it lacks: scoring documents
instead of chunks (EVAL-1), reading the benchmark's questions (EVAL-2a) and grouping the
results by question type and source (EVAL-2b). LlamaIndex 0.14 has no dataset runner, so a
run is a plain loop of `evaluator.evaluate(question, expected_ids)`.

Eval glossary:

- **Question**: one row of `questions.jsonl` (500 rows). Fields: `question_id`,
  `question_type` (10 types), `source_types`, `question`, `expected_doc_ids`, `gold_answer`,
  `answer_facts`.
- **Expected docs**: `expected_doc_ids`, the `dsid_…` documents the answer comes from. 377
  questions expect 1, 93 expect 2 to 10, and 30 expect none (all 20 `info_not_found` and all
  10 `high_level`).
- **Document recall**: the leaderboard's retrieval metric. For one question, the share of its
  expected docs that appear in what we retrieved; averaged over questions. The leaderboard
  ranks on an LLM-judged answer score, with document recall as a tie-break; we can compute
  recall locally, with no model, so it is our inner-loop number.
- **Top k documents**: a retriever returns chunks, and several chunks can come from one
  document. We score the first `k` **distinct** documents in rank order, so a document split
  into many chunks cannot crowd out the rest or count twice. Default `k = 10`.

| Story | Status |
|---|---|
| EVAL-1  `DocumentRetrieverEvaluator` | ✅ |
| EVAL-2a  `load_questions` | ⬜ |
| EVAL-2b  `metrics_report`: overall, per question type, per source, at k = 5, 10, 20 | ⬜ |
| EVAL-3  baseline: every document, `SentenceSplitter(512)`, local embedder  *(module-level)* | ⬜ |

---

## EVAL-1  `DocumentRetrieverEvaluator`  ✅

**Status:** Done

**As a** RAG developer
**I want to** LlamaIndex's `RetrieverEvaluator` to score the first `top_k_docs` distinct
source documents instead of chunk ids
**So that** every index we build is scored the way the leaderboard scores it, with library
metrics

**Acceptance Criteria (Gherkin)**
- Given chunks from docs `[a, a, a, b]` and `top_k_docs = 2`, Then `retrieved_ids` is `[a, b]`
  and recall for expected `[b]` is 1.0: chunks of one document take one place
- Given docs `[a, b, c]`, `top_k_docs = 2` and expected `[c]`, Then recall 0.0: `c` is third
- Given docs `[a]` and expected `[a, b]`, Then recall 0.5
- Given chunks `[a, a, a, b]` and expected `[b]`, Then mrr 0.5: `b` is the 2nd document even
  though it is the 4th chunk
- Given chunks `[a, b, a]`, Then `retrieved_texts` holds each document's best chunk once
- Given `top_k_docs = 0`, Then a validation error
- Given a chunk with no source document, Then `ValueError` naming the chunk: it cannot be
  scored, and dropping it silently would hide a broken index

**Example with real data**
`qst_0431` (completeness): "What is the procedure for an emergency rollback of a Serving
Runtime release (Hosted and Dedicated)?" expects `dsid_f6e3b7ad…` "Emergency rollback:
Serving Runtime (Hosted + Dedicated)" (4,429 chars, several chunks at 512 tokens) and
`dsid_840703a1…` "Runtime release pipeline: rollback procedure". A retriever whose top 10
documents hold only the first scores recall 0.5 on it.

**Non-functional Requirements**
- Shared NFRs. No network, no model: the tests use a fixed retriever, the doctest a
  `SummaryIndex`.
- Reuse: `RetrieverEvaluator` and its metrics unchanged; the override is its one hook,
  `_aget_retrieved_ids_and_texts`. A node postprocessor could not do this, because the
  evaluator reads `node_id`, and a chunk's `node_id` is never a dsid.
- Replaces the first version of this story (`document_recall`, a function around `Recall`),
  which re-did what the evaluator already does.

**Dependencies**
- APIs: `DocumentRetrieverEvaluator.from_metric_names(names, retriever=..., top_k_docs=10)`
  in `pipeline/eval/evaluator.py`; each node's `ref_doc_id` must be its dsid, so EVAL-3
  builds `Document(id_=doc_id)`
- Uses: `llama_index.core.evaluation.RetrieverEvaluator`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## EVAL-2a  `load_questions`  ⬜

**Status:** To do

**As a** RAG developer
**I want to** `load_questions(path)` to return the benchmark questions that have expected
docs, as small typed records, and say how many it left out
**So that** every run scores the same 470 questions, and a changed answer key fails a test

**Acceptance Criteria (Gherkin)**
- Given a line with expected docs, Then a `Question(question_id, question_type,
  source_types, text, expected_doc_ids)`
- Given a line with no expected docs, Then it is left out and counted in `skipped`
- Given the real file, Then 470 questions and 30 skipped, and the file's sha256 is
  `f9524b91…d3d147905` (a golden: a new release of the answer key fails it on purpose)

**Example with real data**
`qst_0431` → `Question("qst_0431", "completeness", ("confluence",), "What is the procedure
for an emergency rollback…", ("dsid_f6e3b7ad…", "dsid_840703a1…"))`. `qst_0471`
(`info_not_found`, no expected docs) → skipped.

**Non-functional Requirements**
- Shared NFRs. Reads one file; no network. `gold_answer` and `answer_facts` are not loaded:
  they belong to answer scoring, not retrieval.
- The file moves to `data/_full/questions.jsonl`, beside `documents.parquet` (it was under
  `data/linear/` only because the Linear work downloaded it; it covers every source).

**Dependencies**
- APIs: `load_questions(path) -> LoadedQuestions(questions: list[Question], skipped: int)` in
  `pipeline/eval/questions.py`
- Service Bus: N/A · Database: N/A · UI: N/A

---

## EVAL-2b  `metrics_report`  ⬜

**Status:** To do

**As a** RAG developer
**I want to** one table of mean `hit_rate`, `recall`, `mrr`, `ndcg` at k = 5, 10 and 20,
overall, per question type and per source
**So that** a run says not only how good retrieval is but where it fails

**Acceptance Criteria (Gherkin)**
- Given evaluation results for each question and k, Then one row per (group, k) with the
  mean of each metric and the number of questions in the group
- Given a question with two source types, Then it counts in both source groups: 68 of the
  470 questions span 2 to 5 sources, so source rows add up to more than 470
- Given recall@20 well above recall@10 for a group, Then that group's docs are found but
  ranked too low (a ranking problem, not a missing-document problem)

**Example with real data**
Group sizes on the real file: overall 470; by source confluence 114, jira 100, slack 79,
github 60, google_drive 60, linear 58, gmail 55, hubspot 34, fireflies 25; by type basic
175, semantic 125, intra_document_reasoning 40, project_related 40, constrained 30,
conflicting_info 20, completeness 20, miscellaneous 20.

**Non-functional Requirements**
- Shared NFRs. Pure: results in, rows out. Writing a run's files is EVAL-3.

**Dependencies**
- APIs: `metrics_report(results) -> list[ReportRow]` in `pipeline/eval/report.py`
- Uses: EVAL-1's `RetrievalEvalResult.metric_vals_dict`, EVAL-2a's `Question`
- Service Bus: N/A · Database: N/A · UI: N/A

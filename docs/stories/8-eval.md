# Eval stories

How we score retrieval on EnterpriseRAG-Bench, across every source. Rules and template:
[stories.md](../stories.md).

Why this comes first: the plan is a naive baseline (every document, `SentenceSplitter(512)`,
a local embedder, no cleaning) and then one clean-up story at a time. A clean-up story is
only worth merging if it moves a number, so the number has to exist before the baseline.

Eval glossary:

- **Question**: one row of `questions.jsonl` (500 rows, kept at `data/linear/questions.jsonl`).
  Fields: `question_id`, `question_type` (10 types), `source_types`, `question`,
  `expected_doc_ids`, `gold_answer`, `answer_facts`.
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
| EVAL-1  `document_recall` | ✅ |
| EVAL-2  recall report: overall, per question type, per source  *(module-level)* | ⬜ |
| EVAL-3  baseline: every document, `SentenceSplitter(512)`, local embedder  *(module-level)* | ⬜ |

---

## EVAL-1  `document_recall`  ✅

**Status:** Done

**As a** RAG developer
**I want to** `document_recall(ranked_doc_ids, expected_doc_ids, k)` to return the share of a
question's expected docs found in the first `k` distinct retrieved docs
**So that** every index we build is scored the way the leaderboard scores it

**Acceptance Criteria (Gherkin)**
- Given retrieved `[a, b]` and expected `[a]`, When k = 10, Then 1.0
- Given retrieved `[a, a, a, b]` (three chunks of `a`) and expected `[b]`, When k = 2, Then 1.0:
  chunks of one document count as one place
- Given retrieved `[a, b, c]` and expected `[c]`, When k = 2, Then 0.0: `c` is third
- Given retrieved `[a]` and expected `[a, b]`, Then 0.5
- Given expected `[]`, Then `None`: the question has no expected docs, so it is left out of
  the average rather than scored 0 or 1
- Given retrieved `[]` and expected `[a]`, Then 0.0 (LlamaIndex's `Recall` raises on an empty list)
- Given k = 0, Then `ValueError`

**Example with real data**
`qst_0431` (completeness): "What is the procedure for an emergency rollback of a Serving
Runtime release (Hosted and Dedicated)?" expects `dsid_f6e3b7ad…` and `dsid_840703a1…`. A
retriever whose top 10 docs hold only the first scores 0.5 on it. `qst_0001` (basic) expects
one doc, so it scores 0 or 1.

**Non-functional Requirements**
- Shared NFRs. Pure: lists in, a float out; no disk, no network.
- Reuse: the recall arithmetic is LlamaIndex's `Recall` retrieval metric
  (`llama_index.core.evaluation.retrieval.metrics`). Our code adds only what it lacks: collapse
  chunks to distinct documents, cut at `k`, and skip questions with no expected docs, and score
  an empty retrieval 0 (`Recall` raises on either empty list).

**Dependencies**
- APIs: `document_recall(ranked_doc_ids: Sequence[str], expected_doc_ids: Sequence[str], k: int = 10) -> float | None`
  in `pipeline/eval/recall.py`
- Uses: `llama_index.core.evaluation.retrieval.metrics.Recall`
- Service Bus: N/A · Database: N/A · UI: N/A

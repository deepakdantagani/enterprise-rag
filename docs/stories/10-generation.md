# Generation stories (GEN-n): answers the leaderboard scores

Rules and template: [../stories.md](../stories.md). The retrieval these stories build on is
**v4** (EVAL-3l, [8-eval.md](8-eval.md)): dense `voyage-4-lite` + BM25 over the same titled
chunks, RRF over 200-deep lists, the top 100 reranked by `rerank-3-lite`, recall@10 0.834.

Why this file exists: the EnterpriseRAG-Bench leaderboard ranks **answers**, not retrieval.
Until GEN-7 we have no leaderboard-comparable number, only recall.

Glossary (enough to read any story here cold):
- **Leaderboard**: huggingface.co/spaces/onyx-dot-app/EnterpriseRAG-Bench-Leaderboard, 29 systems
  (2026-09-29). 1st: Mixedbread + Opus 5, 86.58. 10th: SovraRAG.ch, **65.61** (our target).
  The benchmark's own one-shot baseline, "BM25 + GPT-5.4", scores 50.6.
- **Answer file**: what a system submits, one JSON line per question:
  `{"question_id": "qst_0001", "answer": "...", "document_ids": ["dsid_...", ...]}`
  (EnterpriseRAG-Bench `answer_evaluation/README.md`).
- **Official scorer**: EnterpriseRAG-Bench `src/scripts/answer_evaluation/metrics_based_eval.py`.
  An LLM judge (default `gpt-5.4`) grades each answer; it writes `results.json` with one row per
  question: `answer_correct` (true/false), `completeness_pct`, `document_recall_pct`,
  `invalid_extra_docs`.
- **Correctness**: the judge's yes/no on "does the answer agree with the gold answer". Extra
  detail is fine; any quantity in both answers must match; missing a core part is a no.
- **Completeness**: the share of the question's `answer_facts` the answer contains, each fact
  judged alone.
- **Overall score**: the leaderboard's ranking number, the mean over all 500 questions of
  `correct (0 or 1) × completeness %`. A wrong answer scores 0 however complete it is.
- **Answerer**: our LLM that writes answers (local `gemma4:26b` on Ollama first, $0). Not the
  judge.
- **Replay retriever**: `pipeline/eval/rerank.py` `replay_retriever`, v4's saved top 100 chunks
  per question in their saved rerank order, for $0 (RET-5). Saved for the 470 questions that
  have expected documents.

## GEN-1  How the leaderboard scores answers  ✅

**Status:** Done (research; no code)

**As a** developer aiming for a top-10 place,
**I want to** know exactly how the leaderboard turns answers into its number,
**so that** every later story optimises the real target.

**Findings** (EnterpriseRAG-Bench repo `methodology.md`, `metrics_based_eval.py`,
`src/prompts/answer_evaluation.py`; leaderboard space `transform_raw_data.py`):
- Overall score = mean over **500** questions of `answer_correct × completeness_pct`
  (`transform_raw_data.py`, `overall_scores.append(binary_correct * completeness)`).
  Recomputed from the published results files: BM25 + GPT-5.4 **50.6**, Mixedbread **86.58**,
  both equal to the leaderboard.
- The judge (`gpt-5.4` by default, env `LLM_MODEL_NAME`) strips citations first, then asks
  `ANSWER_WHOLISTIC_EVALUATION_PROMPT` (correctness) and, per fact,
  `INDIVIDUAL_FACT_VALIDATOR_PROMPT` (completeness).
- Document recall and invalid extra documents are shown but are **not** in the overall score.
  Submitted documents that differ from the gold set go through a 3-judge correction vote.
- The 30 questions with no expected documents count: 20 `info_not_found`, whose one fact is
  "the answer must state … the query is not fully answerable" (e.g. `qst_0481`), and 10
  `high_level` (e.g. `qst_0471` "What is Redwood Inference's mission statement?").
- The baseline answerer gives the LLM the top 10 **full documents** as
  `--- Document n (ID: dsid) ---` / `Title: …` / content, with a 4-sentence prompt
  (`src/prompts/vector_search_answer_gen.py`).

**Dependencies:** none (N/A: Service Bus, database, UI).

## GEN-2a  `first_documents` and `document_block`  ✅

**Status:** Done

**As a** developer building the answerer,
**I want to** turn v4's ranked chunks into the first 10 distinct documents, each formatted the
way the benchmark's baseline shows documents to its LLM,
**so that** the answerer reads whole documents in rank order, like the baseline it is
compared with.

**Acceptance Criteria**
```gherkin
Scenario: the first ten distinct documents, in rank order
  Given ranked chunks from documents 3, 3, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11
  When first_documents runs
  Then it returns documents 3, 0, 1, 2, 4, 5, 6, 7, 8, 9

Scenario: fewer than ten documents
  Given ranked chunks from documents 1 and 2
  Then it returns 1, 2

Scenario: one document block
  Given number 1, id dsid_a, title "Q3 budget", content "Priya approved it."
  Then document_block returns "--- Document 1 (ID: dsid_a) ---\nTitle: Q3 budget\n\nPriya approved it."

Scenario: real data
  Given v4's saved reranked chunks for qst_0001
  Then first_documents returns 10 ids, the gold dsid_ae068ee4aa9640159427cd941bef0238 first
```

**Example with real data** (`qst_0001`, "What are the default size limits for file uploads and
total request size for the new multipart upload support on the OpenAI-compatible API
endpoints?"): v4's reranked chunks reach 10 distinct documents after 14 chunks. 1 is the gold
`dsid_ae068e…` (GitHub, "add multipart/form-data handling, strict content-type valida…", 5,120
characters); 8 of the 10 are GitHub PRs, 2 are Slack `docs` channel documents.

**Measured** (all 470 saved questions): every one reaches 10 documents, within 11 chunks at the
median and 27 at most; the fewest distinct documents in a top 100 is 39.

**What changed:** `pipeline/eval/answers.py`. `first_documents` is
`list(dict.fromkeys(ids))[:10]`: a set that keeps first-seen order, so a document ranks where its
best chunk ranks (a plain `set` would lose the order). The chunk texts are dropped; the answerer
reads whole documents (GEN-2b).

**Non-functional Requirements:** shared ones; pure functions, no I/O.

**Dependencies:** `NodeWithScore.node.ref_doc_id` (LlamaIndex); input from `replay_retriever`.

## GEN-2b  `documents_by_id`  ✅

**Status:** Done

**As a** developer building the answerer,
**I want to** read the title and content of a few documents by id from the corpus parquet,
**so that** the answerer can show full documents, not only the chunks that matched.

**Acceptance Criteria**
```gherkin
Scenario: only the asked documents are returned
  Given a parquet with documents a, b, c
  When documents_by_id asks for a and c
  Then it returns {a: (title, content), c: (title, content)}

Scenario: blank title
  Given a document whose title is null
  Then its title is ""

Scenario: real data
  Given data/_full/documents.parquet and qst_0001's 10 document ids
  Then all 10 come back; dsid_ae068e… has 5,120 characters of content
```

**Example with real data:** the parquet holds 511,957 documents; one answer needs 10. A full
top 10 is 14K tokens at the median and 35K at most over the 470 questions (chunks alone:
5K / 13K), measured 2026-09-29.

**Measured** (2026-09-30): the parquet has 511,962 rows but 511,958 distinct ids; 4 ids each
name two different documents (a benchmark data slip), e.g. `dsid_8a0c5430…` is both "Signal Peak
Logistics — Account Brief (Renewal + Expansion) — 2026-03-18" (1,534 chars) and "Signal Peak
Logistics" (3,645 chars); 1 of the 4 is among the 4,532 documents of the 470 top 10s. The file
is one 1.4 GB row group, so any read scans it all (1.2 s). 161 titles have surrounding spaces;
6 of the 4,532 documents open with their own title (2 titles over 500 characters).

**Decisions:** an id with two documents returns both texts, the second after the first (the
judge knows only the id, and the chunk may have matched either). Read once for every question's
ids, not per question (~10 min saved over 500). Titles stay as the baseline shows them, even when
the content repeats them (6 documents, ≤1K tokens).

**Non-functional Requirements:** shared ones; reads only the needed rows (pyarrow `filters`).
15 documents have blank titles (EVAL-3i), none in the 470 top 10s.

**Dependencies:** `data/_full/documents.parquet` (`doc_id`, `title`, `content`).

## GEN-2c  `FullDocuments` node postprocessor  ✅

**Status:** Done

**As a** developer building the answerer,
**I want to** a LlamaIndex `BaseNodePostprocessor` that replaces ranked chunks with one node per
document (the first 10), whose text is its `document_block` and whose metadata holds `doc_id`,
**so that** the query engine gives the LLM full documents without custom glue around it.

**Acceptance Criteria**
```gherkin
Scenario: chunks become numbered full documents
  Given chunks from dsid_5, dsid_5, dsid_2 and their titles and contents
  When FullDocuments post-processes them
  Then it returns two nodes: "--- Document 1 (ID: dsid_5) ---…", "--- Document 2 (ID: dsid_2) ---…"
  And each node's metadata doc_id is its document id
```

**Example with real data:** `qst_0009` (Gmail, "In the EdgePath evaluation email thread, what
alternative Year 1 pricing package did Redwood propose …?"): 14 chunks become 10 document nodes.
Node 1 is `dsid_85deb10a…`, "Licensing offsets & packaging for potential migration", the whole
5-email thread (8,350 characters). The top chunk held only Avery's reply; the node also holds
Sarah's email with the competitor's offer ("CloudOrbit … 50% discount … $60k migration credit").

**Decisions:** `TextNode` (the synthesizer reads `.text`); node id = document id; `doc_id` kept in
metadata for the answer file but in `excluded_llm_metadata_keys`, so the LLM does not read it
twice; a document missing from `documents` raises `KeyError` (the run loads all of them first).

**Non-functional Requirements:** shared ones; custom logic only as a LlamaIndex postprocessor.

**Dependencies:** GEN-2a, GEN-2b; `BaseNodePostprocessor`.

## GEN-2d  `ANSWER_PROMPT` and `answer_row`  ✅

**Status:** Done

**As a** developer,
**I want to** a `RetrieverQueryEngine` (replay retriever → `FullDocuments` → compact response
synthesizer with our prompt) and `answer_row`, which returns one answer-file line,
**so that** one question becomes one leaderboard-format answer.

The prompt (a `PromptTemplate`, `text_qa_template`); each rule comes from the judge prompts or
a question type (GEN-1):

```
You are a precise assistant answering questions about Redwood Inference, using documents
from the company's internal systems (Slack, Gmail, Linear, Jira, Confluence, GitHub,
Google Drive, HubSpot, meeting transcripts). The documents come from an imperfect search:
many will be irrelevant, and some may be outdated or duplicated.

Rules:
1. Use only the documents. Never add facts from outside them or guess.
2. Answer every part of the question. Copy exact values as written: names, numbers,
   units, dates, versions, IDs, flags and config keys.
3. Respect every qualifier in the question (team, customer, date, version, environment).
   Ignore documents that match the topic but fail a qualifier.
4. If the question asks for a list or "all", include every matching item from all documents.
5. If documents disagree, give each value, say where each comes from, and say which is
   newer or more authoritative.
6. If the documents do not contain the answer, say so plainly in the first sentence
   ("The documents do not say ..."). You may then add closely related facts you did find.
7. Include every detail the documents give that answers the question. No preamble,
   no citations, no markdown.

## Documents
{context_str}

## Question
{query_str}

## Answer
```

| Rule | Why (source) |
|---|---|
| 1 | Completeness facts include "must not say…" facts that catch made-up answers |
| 2 | Correctness: "specific quantities mentioned in both answers must match" |
| 3 | 30 `constrained` questions: qualifiers rule out all but one document |
| 4 | 20 `completeness` and 40 `project_related` questions need every item |
| 5 | 20 `conflicting_info` questions: "requires … a complete and correct answer" |
| 6 | 20 `info_not_found` questions; the benchmark's agent prompt: "say so explicitly" |
| 7 | Completeness scores every missing fact and the judge allows extra detail; a 1-3 sentence limit dropped `qst_0009`'s 99.9% SLO fact |

**Acceptance Criteria**
```gherkin
Scenario: the leaderboard answer format
  Given a replay retriever with documents dsid_1, dsid_2 and an LLM that answers " Priya approved the Q3 budget. "
  When answer_row runs for q1
  Then it returns {"question_id": "q1", "answer": "Priya approved the Q3 budget.", "document_ids": ["dsid_1", "dsid_2"]}

Scenario: what the LLM is sent
  Then the prompt holds rule 1, "--- Document 1 (ID: dsid_1) ---\nTitle: …", and "## Question\nWho approved the Q3 budget?"
```

**Example with real data:** `qst_0001` on `gemma4:26b` (10K-token prompt, 7.9 s): "The default
limits for multipart/form-data on the OpenAI-compatibility endpoints are 10MiB per file and 50MiB
for the total request size." Gold: 10 MiB per file, 50 MiB per request.

**Measured** (`qst_0009`, Gmail, real code): with rule 7 as "1-3 sentences" the answer held 3-4 of
the 5 answer facts (it dropped "99.9% latency SLO for hosted US instances"); with "include every
detail" (25.7 s) it holds 4 clearly, the fifth ("did not match the 50% + $60k") implied.

**Retrieval inside the engine:** the replay retriever returns v4's saved top 100 in its saved
`rerank-3-lite` order, so answers use v4's exact ranking for $0; a live system would put the hybrid
retriever and `VoyageAIRerank` in its place.

**Non-functional Requirements:** shared ones, except it calls a model (local, $0). Ollama
`gemma4:26b`, `temperature=0` (same prompt, same answer, so score changes come from our changes), `thinking=False` (base case; a later story compares thinking on), `context_window=40_960`: Ollama's default window
would cut the 35K-token prompts silently. `document_ids` are the 10 documents shown (as the
baseline); letting the LLM choose them is a later story, as they are not in the score.

**Dependencies:** GEN-2c; `RetrieverQueryEngine`, `PromptTemplate`, `llama_index.llms.ollama`.

## GEN-2e  `save_answers` (resumable)  ✅

**Status:** Done

**As a** developer running 500 local answers (~1.5 h),
**I want to** write each answer to `answers.jsonl` as soon as it is made and skip questions
already there,
**so that** a crash or a re-run never asks the LLM again for a finished question.

**Acceptance Criteria**
```gherkin
Scenario: resume
  Given answers.jsonl already holds q1
  When save_answers runs for q1 and q2
  Then only q2 is answered, and it returns 1

Scenario: nothing new
  When save_answers runs again for q1 and q2
  Then the LLM is not called and it returns 0
```

**Example with real data:** the same pattern as `save_completions` (RET-7), which planned 470
questions across restarts.

**Non-functional Requirements:** shared ones; one flushed line per answer.

**Measured:** both scenarios green with a recording LLM: resuming from a file holding q1 sends
exactly one prompt (q2); a second run sends none and returns 0. `save_answers` in
`pipeline/eval/answers.py` (18 lines), each line is `answer_row`'s dict.

**Dependencies:** GEN-2d. Output `data/_index/answers/<run>.jsonl` (gitignored).

## GEN-3  `all_questions`  ⬜

**Status:** To do

**As a** developer,
**I want to** load all 500 questions, including the 30 that expect no document,
**so that** the answer file covers every question the leaderboard averages over.

`load_questions` (EVAL-2a) skips those 30 on purpose, because document recall has nothing to
count for them. The overall score counts them, and an answer of "the documents do not say"
scores 100 on an `info_not_found` question.

**Acceptance Criteria**
```gherkin
Scenario: every question
  Given questions.jsonl
  Then all_questions returns 500 questions: 470 with expected documents, 20 info_not_found, 10 high_level
```

**Example with real data:** `qst_0481` (info_not_found) asks for allowlisted accounts and budget
values that no document holds; its one fact requires the answer to say it is not fully
answerable.

**Dependencies:** `pipeline/eval/questions.py`.

## GEN-4  Retrieve the 30 missing questions  ⬜

**Status:** To do (paid: ask first)

**As a** developer,
**I want to** run v4 retrieval once for the 30 questions without saved candidates and append
them to the saved candidates and reranks,
**so that** the replay retriever covers all 500 questions.

**Acceptance Criteria**
```gherkin
Scenario: complete coverage
  Then lite_titles_top100_candidates.jsonl and lite-titles-top100-rerank-3-lite.jsonl hold 500 questions
  And the 470 existing rows are unchanged (same sha256 per row)
```

**Example with real data:** the candidates file holds 470 rows today.

**Non-functional Requirements:** cost before running: 30 question embeddings with `voyage-4`
(~$0.001, the saved vectors cover only 470) and 30 × 100 chunks reranked by `rerank-3-lite`
(~1.5M tokens from the free pool).

**Dependencies:** GEN-3; Qdrant `titles__voyage_4_lite__bm25`.

## GEN-5  First answer run (`gemma4:26b`)  ⬜

**Status:** To do

**As a** developer,
**I want to** answer all 500 questions with the local answerer,
**so that** there is a complete answer file to judge.

**Acceptance Criteria**
```gherkin
Scenario: a complete answer file
  Then answers.jsonl holds 500 rows, each with question_id, a non-empty answer, and 10 document_ids
```

**Non-functional Requirements:** ~10 s a question on this Mac, ~1.5 h, $0; logs to the run log.

**Dependencies:** GEN-2e, GEN-4.

## GEN-6  `overall_score`  ⬜

**Status:** To do

**As a** developer,
**I want to** the leaderboard's formula as a pure function over the official scorer's
`results.json`,
**so that** our number is computed exactly as the leaderboard computes it.

**Acceptance Criteria**
```gherkin
Scenario: a wrong answer scores zero
  Given one question, answer_correct false, completeness 100
  Then overall_score is 0.0

Scenario: a correct answer scores its completeness
  Given answer_correct true, completeness 75
  Then overall_score is 75.0

Scenario: published results
  Given the leaderboard's results_bm25.json and results_mixedbread.json
  Then overall_score is 50.6 and 86.58
```

**Dependencies:** published results in `data/_leaderboard/` (gitignored), skipped when absent.

## GEN-7  Official judge run  ⬜

**Status:** To do (paid: ask first)

**As a** developer,
**I want to** run the benchmark's `metrics_based_eval.py` on our `answers.jsonl` and score the
result with GEN-6,
**so that** we have our first leaderboard-comparable number and a per-question list of wrong
and incomplete answers to improve.

**Acceptance Criteria**
```gherkin
Scenario: first score
  Then results.json holds 500 rows and overall_score is recorded in docs/eval/results.md
```

**Non-functional Requirements:** needs an OpenAI key (the default judge `gpt-5.4`); cost
estimated from the 500 questions' fact counts before running. Run with `--no-correction` first,
so the gold set stays fixed while we compare our own versions.

**Dependencies:** GEN-5, GEN-6.

## GEN-8a  `live_retriever`: v4 for a new question  ✅

**Status:** Done

**As a** developer trying the answerer by hand,
**I want to** run v4's retrieval live for any question, not only the 470 saved ones,
**so that** the ask page (GEN-8b) can answer whatever is typed.

The saved v4 results were made by `hybrid_retriever(store, voyage-4, "rrf", top_k=200)[:100]`,
then `rerank-3-lite` over those 100 (EVAL-3k). Live, the same thing is LlamaIndex parts only:

```
engine.query(question)                         ← LlamaIndex RetrieverQueryEngine (answer_engine, already built)
  1. live_retriever  → 100 chunks              ← LlamaIndex QueryFusionRetriever: dense (voyage-4 question
                                                  vector) 200 + BM25 200, RRF, top 100, on titles__voyage_4_lite__bm25
  2. VoyageAIRerank  → the 100 reordered       ← LlamaIndex postprocessor, rerank-3-lite
  3. FullDocuments   → 10 whole documents      (already built)
  4. synthesizer     → ANSWER_PROMPT + gemma4  (already built)
```

**Acceptance Criteria**
```gherkin
Scenario: the live top 100 is the saved top 100
  Given qst_0001 and its saved voyage-4 question vector
  When live_retriever retrieves it
  Then it returns the same 100 chunk ids, in the same order, as lite_titles_top100_candidates.jsonl

Scenario: a document that was not preloaded
  Given FullDocuments with a corpus path and a top 10 holding a document not loaded yet
  Then it reads the missing documents from the corpus in one pass and keeps them

Scenario: a benchmark question costs no embedding
  Given a question in the saved voyage-4 question vectors
  Then Voyage's embedding API is not called
```

**Measured** (2026-09-30): live on `qst_0001` with its saved question vector, the top 100 is
the saved top 100, same chunks in the same order (2.5 s). `VoyageAIRerank` sends each chunk as
`get_content(MetadataMode.EMBED)`, which here equals the plain chunk text the saved rerank sent
(the chunks' `source_type` and `title` metadata are excluded from embedding). A live question can
land on any of the 511,962 documents, so `FullDocuments` takes an optional corpus path and reads
the documents it was not given, all missing ids in one pass (1.2 s), keeping them.

**Non-functional Requirements:** a new question costs one `voyage-4` query embedding (~30 tokens,
~$0.000002) and one `rerank-3-lite` call over 100 chunks (~50K tokens, from the free pool while it
lasts, then ~$0.001). Exact search, as in evaluation (53 ms a question).

**Dependencies:** `llama-index-postprocessor-voyageai-rerank` (new); Qdrant
`titles__voyage_4_lite__bm25`; `data/_index/question_embeddings/voyage-4.jsonl`; `VOYAGE_API_KEY`
from `.env`.

## GEN-8b  Ask page (Gradio) with Phoenix traces  ✅

**Status:** Done

**As a** developer,
**I want to** a local page where I type a question and read the answer, the 10 documents it used,
and, for a benchmark question, the gold answer and its facts,
**so that** I can check answers by hand before paying for the official judge.

```
Gradio page: type a question
  └─ ask(question)
       └─ engine.query(question)               ← LlamaIndex RetrieverQueryEngine: GEN-8a live retriever + rerank,
                                                  FullDocuments, ANSWER_PROMPT, gemma4
  └─ shows: answer · 10 documents (id, source, title) · gold answer + answer_facts when the question is a benchmark one
  └─ every step traced to Phoenix (trace_to_phoenix, EVAL-4) → http://localhost:6006
```

**Acceptance Criteria**
```gherkin
Scenario: a benchmark question shows its gold answer
  Given the question of qst_0009
  Then the page shows our answer, 10 documents with dsid_85deb10a… first, the gold answer and 5 facts

Scenario: a new question
  Given "What is Redwood Optimize?"
  Then the page shows our answer and 10 documents, and no gold answer
```

**Non-functional Requirements:** demo quality: a polished, product-grade interface a VC would sign
off as the final user experience (Deepak, 2026-09-30), not a developer form: clear hierarchy, the
answer first, sources as readable cards with their source system, a visible progress state during
the ~25 s answer, example questions to start from, light and dark themes. ~25 s an answer on
gemma4; runs on localhost only.

**Measured** (2026-09-30, real page, `uv run python -m pipeline.eval.ask_page`):
- `qst_0009`: search + rerank 2.5 s, answer 31.9 s cold / 7.7 s warm; the answer holds all five
  parts of the gold package; source 1 is the EdgePath thread (Gmail).
- "What is Redwood Optimize?" (not a benchmark question, the only kind that calls Voyage for its
  vector): 10 sources from Fireflies, Slack and Google Drive; 32.0 s, most of it gemma4 reading
  ~14K tokens before its first word.

**Decisions made while building:**
- The page streams: status line, then the 10 source cards (~3 s), then the answer as it is
  written. The LLM is read on a thread so the clock keeps moving before the first word; Gradio's
  own progress bars are hidden.
- Gmail documents are stored as a Python list string (`['From: …\\nTo: …', …]`, some with the
  line break escaped twice): the cards show their opening as plain text; the LLM still gets the
  document as stored, as the benchmark's baseline did.
- gemma4 writes markdown bullets and bold despite rule 7; the page renders `- `, `* ` and `**…**`.
- `FullDocuments` keeps each document's source system (from its best chunk) for the cards.

**Dependencies:** GEN-8a; `gradio` 6.29 (new); Phoenix (`uv run --with arize-phoenix phoenix serve`).

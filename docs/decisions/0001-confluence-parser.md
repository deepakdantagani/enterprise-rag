# 0001. Parse Confluence exports with markdown-it-py + a plain-label heading rule

Date: 2026-09-13. Status: accepted.

## Decision

Use **markdown-it-py** (CommonMark + tables) as the parser, with a small **plain-label heading rule** applied to files that carry no heading markup, wrapped in a LlamaIndex `NodeParser` (`pipeline/nodes.py`). No hosted or model-based parser.

## Why

The corpus is 5,189 plain-text Confluence exports. After preprocessing they fall into four buckets:

| Bucket | Files | Structure present |
|---|---|---|
| A | 1,645 (31.7%) | `#` headings |
| B | 781 (15.1%) | Setext (underlined) headings |
| C | 2,751 (52.9%) | Lists, tables, code, but headings are bare lines like `Overview` |
| D | 12 (0.3%) | Prose only |

Every parser handles A and B. The deciding question was C, and only the label rule recovers those headings.

Validation on 12 hand-labeled sample files covering every bucket and every awkward shape found in the corpus (escaped `\n` bodies, tables without separator rows, checkboxes, blockquotes, a 104-byte file, the 25 KB largest file):

| Parser | Heading F1 | Table cells | Code blocks | Text coverage | Source line ranges |
|---|---|---|---|---|---|
| markdown-it | 64% | 100% | 100% | 100% | yes |
| **markdown-it + label rule** | **98%** | 100% | 100% | 100% | yes |
| Docling 2.126 | 62% | 96% | 100% | 99% | no |
| Unstructured 0.27 (md) | 64% | 96% | 100% | 96% | no |
| LlamaParse (fast tier) | 64% | 100% | 100% | 100% | no |

Nothing loses content; the difference is entirely headings. On the six bucket-C/D files every off-the-shelf parser scored 0% heading F1; the label rule scored 100%.

The label rule was also checked against the 25,155 `#` headings in bucket A with the markers stripped: recall 0.83 overall, 0.92 excluding numbered headings (which the chunker keeps with their body anyway). Precision on a random 40-detection sample from bucket C was about 37/40, judged by hand. Remaining known gap: precision is estimated, not measured; a 30-file random hand-labeled sample would settle it.

## Rejected

- **LlamaParse** (fast and agentic tiers): byte-for-byte pass-through on `.txt` input. Adds cost and a network dependency, returns no source line ranges.
- **Docling**: no heading gain, dropped ~25% of table cells on two files, empty provenance on text input.
- **Unstructured**: no heading gain in Markdown mode; plain-text mode invented titles from table headers and JSON fragments. Needs a spaCy model download.
- **Local LLM structure inference (Gemma 4 26B via Ollama, single- and two-pass prompts)**: 23-29 of 29 expected labels on three excerpts in the best run, but parent-link assignment regressed in the two-pass design, runs took ~20 s per excerpt, and outputs were not deterministic. Not worth it when a 30-line rule reaches 98% F1.

## Preprocessing that made the parser work

Found during validation and now in `pipeline/preprocess.py`: JSON-string-escaped bodies (910 files, detected when literal `\n` outnumbers real newlines), numbered setext headings that CommonMark reads as list items (44), pipe tables with no separator row (474), and Confluence wiki markup `h2.` / `||a||` (131 / 33).

## Consequences

- Files the triage gate flags (117 today, 2.3%) are still chunked, as plain paragraphs with the title prefixed. Nothing is excluded from the index; the review list is a to-do, not a blocker.
- Sub-list indentation errors in the source no longer matter: lists are atomic in the chunker.
- If the corpus changes shape, rerun `python -m pipeline.triage`; new flag types are the signal to revisit this record.

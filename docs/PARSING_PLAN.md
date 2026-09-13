# Document Parsing — End-to-End System Design

Status: proposed design for review. No parser implementation is authorized by this document alone.

## 1. Objective and system boundary

Convert each ingested Confluence document into ordered, inspectable content blocks that preserve meaning, structure, and exact source locations. The output must support later chunking, precise citations, and selective reprocessing.

The parsing subsystem starts with an existing ingestion record and ends with a validated, versioned parsed document. Chunk sizing, embeddings, retrieval, answer generation, and deployment are separate work. Parsing quality supports the [project goal](../PROJECT_GOAL.md); it cannot by itself establish a top-10 benchmark ranking.

This design follows requirements → constraints → contracts → processing → failure handling → security → validation → rollout. It applies the findings in [Document Parsing Research](DOCUMENT_PARSING_RESEARCH.md). Choices described below are project proposals, not claims of a universal enterprise standard.

## 2. Current constraints and assumptions

| Item | Current evidence or constraint |
|---|---|
| Corpus | 5,189 Confluence text exports; approximately 51.2 MB of original text. |
| Input | Local JSONL containing `doc_id`, `source_type`, `source_path`, and `raw_content`. |
| Dataset provenance | GitHub v1.0.0 exports; equivalence to current Hugging Face data remains unverified. |
| Structure | Mixture of Markdown and plain labels, tables, lists, code, and literal escapes. Existing counts are heuristic. |
| Missing metadata | Native page hierarchy, source versions, update timestamps, and ACLs are not supplied by the current records. |
| Initial execution | Local batch processing, one document at a time; no network or model calls required. |
| Working style | Very small PRs; every change explained and reviewable. |

These constraints support a local file-based implementation first. A service, database, queue, or distributed worker fleet would add decisions before the current workload requires them. Future production capacity and freshness targets must be set from actual workload measurements and requirements.

## 3. Requirements and acceptance criteria

### Functional requirements

1. Preserve the original document and its source identity.
2. Identify ordered blocks: headings, paragraphs, lists, tables, code, and unsupported content.
3. Preserve explicit heading hierarchy; distinguish inferred section labels from explicit structure.
4. Provide exact source spans for every block.
5. Preserve source metadata unchanged when available; represent missing information explicitly.
6. Identify the source content, parser implementation, configuration, and output schema used for each result.
7. Validate results before publication and report individual failures without silently dropping documents.
8. Support reruns, selected-document processing, and replacement of outdated results.

### Quality requirements

| Requirement | Initial acceptance gate |
|---|---|
| Source fidelity | Every block's source text equals its referenced raw-text slice. |
| Complete accounting | Top-level source spans cover all input characters exactly once, including explicitly retained separators. |
| Citation integrity | All spans are within bounds and resolve against the recorded source hash. |
| Structural fidelity | All agreed expectations in the reviewed fixture set pass; no known critical table, code, or heading defect remains. |
| Repeatability | Identical source and processing identity produce identical semantic output; run timestamps are excluded from comparison. |
| Batch completeness | Each selected record has one terminal outcome: valid, valid with warnings, or failed. |
| Failure visibility | Failed results are not published as valid; full-corpus runs return a failure signal if any record fails. |
| Performance | Record elapsed time, peak memory, and documents per second before setting a numerical target. |

Full character coverage proves preservation, not correct interpretation. Structural checks and manual review remain necessary. No invented 99.9% availability or throughput target is attached to a local batch script.

## 4. Design decisions and alternatives

| Decision | Proposed choice | Reason and reconsideration trigger |
|---|---|---|
| Parsing method | Deterministic, source-aware text parsing. | Current input is text. Reconsider specialized adapters when a different source representation arrives. |
| Markdown handling | Evaluate one maintained parser with source positions on our fixtures before selecting a dependency. | Nested Markdown is difficult to handle correctly with accumulating regular expressions. A dependency must demonstrably simplify the required behavior. |
| Plain labels | Conservative section candidates with inferred origin. | The export cannot reliably reveal original nesting. Expand inference only after reviewing examples. |
| Original versus normalized text | Original remains immutable; derived representations remain separate. | Keeps citations and debugging reliable. |
| Storage | Existing raw files plus versioned local parsed artifacts. | Sufficient for this corpus; no database required now. |
| Execution | Sequential processing initially. | Establish correctness and measure bottlenecks before adding concurrency. |
| LLM enrichment | Deferred. | No measured need; generated text must never silently replace source evidence. |

The parser selection experiment is bounded: use the same small fixture set, check required syntax and source mappings, and choose the smallest approach that passes. It is not a broad framework comparison.

## 5. Data contracts

### Input contract

Consume the existing ingestion fields without renaming them. Require a nonempty document ID, the expected source type, a project-relative source path, and string raw content. Reject duplicate identities within the selected input rather than silently overwriting them. An empty string is a valid empty document with a warning; it is different from a missing field.

Compute SHA-256 over the UTF-8 encoding of `raw_content`, without newline normalization. For this dataset, verify once that this reproduces the retained source file bytes. A content hash identifies captured content, not a native Confluence revision.

### Parsed document contract

| Field group | Proposed contents |
|---|---|
| Identity | Existing `doc_id`, `source_type`, and `source_path`; `content_sha256`. |
| Source metadata | Optional verified source URL/version/update time/page ancestry; retain unknown state where unavailable. |
| Processing | `parser_name`, `parser_version`, `config_sha256`, `schema_version`. |
| Document structure | Optional title with source span and origin; ordered blocks. |
| Result | `valid` or `valid_with_warnings`; structured warnings. Failures belong in the run report, not valid artifacts. |

Run start/end times, retries, and error records belong in a separate run report so repeated parsing can produce identical document artifacts. Do not store invented native source metadata or empty ACL lists that imply unrestricted access.

### Block contract

| Field | Meaning |
|---|---|
| `block_id` | Deterministic identifier scoped to a document's content and parser/configuration/schema identity. |
| `type` | Heading, paragraph, list, table, code, separator, or unsupported. |
| `ordinal` | Source order among top-level blocks. |
| `source_span` | Zero-based Unicode character start and exclusive end in `raw_content`. |
| `line_range` | One-based inclusive source lines, derived from the character span. |
| `source_text` | Exact source slice, including syntax; may later be materialized from the source instead of duplicated. |
| `heading_path` | Ordered references to applicable explicit heading blocks. |
| `section_candidate` | Optional inferred plain-text label, kept distinct from verified heading hierarchy. |
| `attributes` | Type-specific structure, such as heading level, code language, list items, or table rows/cells. |

Nested cells and list items may have spans inside their parent block. They do not participate in the top-level non-overlapping coverage calculation. Define this distinction before implementation so hierarchical structure does not appear to be duplicated content.

The first reviewed contract can omit unused optional fields. Schema extensions must remain explicit and versioned.

## 6. Processing flow

| Step | Processing | Validation or outcome |
|---|---|---|
| 1. Select | Select one ID, a reviewed fixture set, or the full input snapshot. | Report the selected count and reject duplicate identities. |
| 2. Validate input | Validate fields, supported representation, and configured size limits. | Invalid input gets a failed outcome with a reason. |
| 3. Identify | Compute content and processing identities. | Reuse only an existing validated artifact with matching identities. |
| 4. Parse blocks | Identify protected code regions and structural tokens in source order. | Preserve all remaining content, including unknown fragments. |
| 5. Attach structure | Build explicit heading paths and type-specific attributes. | Record inferred labels and unsupported constructs separately. |
| 6. Validate output | Check schema, source slices, coverage, hierarchy references, and identifiers. | Validation failure prevents publication. |
| 7. Write artifact | Write to a temporary file and publish it atomically under its versioned identity. | Partial writes never appear as completed output. |
| 8. Report | Record success, warnings, failure, timing, and reuse. | Selected count reconciles with terminal outcomes. |
| 9. Release | Publish a manifest referencing the validated artifacts for a corpus snapshot. | Downstream consumers use this manifest, not a directory glob. |

For the full-corpus release, require all selected documents to be valid or valid with reviewed warning categories. If failures remain, retain the previous release manifest. Successfully written new artifacts can be reused on the next run without becoming the active corpus prematurely.

## 7. Parsing rules by content type

| Content | Initial rule | Ambiguity/failure behavior |
|---|---|---|
| Title | Preserve an explicit title when present. Treat a first-line title inferred from layout as inferred. | A short configuration fragment must not automatically become a page title. |
| Markdown headings | Preserve explicit levels and maintain a heading stack. | Skipped levels produce no invented intervening headings. |
| Plain labels | Preserve text and mark conservative section candidates. | Do not assign a native heading depth without evidence. |
| Paragraphs | Preserve order and exact source spans. | Do not reflow or rewrite original text. |
| Lists | Preserve ordered/unordered markers, nesting, and continuation lines. | Keep unsupported nesting intact and warn. |
| Tables | Preserve the complete source plus recognized headers, rows, and cells. | Pipes inside code or escaped pipes must not silently become cell boundaries. Unresolved structure remains intact with a warning. |
| Code | Preserve fences, indentation, punctuation, and literal escapes; retain explicit language. | Unclosed fences remain source content with a warning. Heading-like text inside code is not a heading. |
| Links/images | Preserve labels and targets as source content or attributes. | Do not fetch linked resources during parsing. |
| Blank space | Retain as separator spans or attach consistently under a documented convention. | Never lose characters between blocks. |
| Unsupported markup | Preserve exact text and record the unsupported construct. | No silent removal or guessed expansion. |

Table segmentation, repeated table headers, code explanation attachment, and heading prefixes in retrieval text belong to the later chunking policy. Parsing supplies their source relationships; it does not choose token sizes.

## 8. Storage, versioning, and lifecycle

Proposed layout, to create only as implementation reaches each need:

| Artifact | Proposed location/purpose |
|---|---|
| Existing originals | `data/confluence/raw/` and `records.jsonl`; retained unchanged. |
| Parsed artifacts | `data/confluence/parsed/`; immutable results addressed by document and processing identity. |
| Run reports | `data/confluence/parsing_runs/`; outcomes and measurements. |
| Release manifest | Identifies exactly which artifact is active for each document in a corpus snapshot. |
| Small review fixtures | A small repository directory containing approved examples and expected outputs. |

Use a canonical serialization for configuration hashing. Include the adapter implementation and relevant dependency versions in processing identity. Configuration identity excludes run timestamps and unrelated runtime settings.

| Event | Required behavior |
|---|---|
| Same source and processing identity | Reuse the validated artifact; do not duplicate it. |
| Source content changes | Produce a new artifact; activate it through a new release manifest. |
| Parser/configuration/schema changes | Select affected artifacts, reparse, validate, and publish a replacement release. |
| Metadata or ACL changes only | Refresh metadata/access state; reuse parsed content when unchanged. |
| Document deletion | Remove it from the active manifest and notify downstream lifecycle handling. |
| Failed replacement | Never expose partial new output. Mark any retained previous artifact as an older source version rather than implying freshness. |

Absence from a partial selection is not a deletion. Infer deletion only from an authoritative complete inventory or an explicit source deletion event. Downstream indexing must retire obsolete chunks when consuming a replacement release; the parser alone cannot remove search results.

Rollback means repointing to a previously validated manifest. It must not restore revoked permissions or resurrect documents whose deletion must remain enforced. Content versions and current authorization/deletion state are separate concerns.

## 9. Failure handling and observability

Separate malformed input, unsupported structure, validation defects, and transient storage errors. A document with preserved but unsupported structure may be valid with warnings; broken spans or lost content are failures. Deterministic parser defects should not be retried repeatedly without a change.

Continue processing independent documents and provide an end-of-run failure signal. Bound retries for transient I/O errors. Resume by checking validated artifacts, not merely by checking whether a filename exists.

The run report should include counts selected/reused/valid/warned/failed, warning categories, failure reasons, elapsed time, and processing identity. Keep document bodies and sensitive metadata out of routine logs. A later production monitor should detect repeated failures, growing unprocessed work, and freshness violations once actual service targets exist.

## 10. Security and future source adapters

Treat document content as untrusted input. It must never execute code, follow embedded instructions, fetch arbitrary URLs, or change parser configuration. Restrict file resolution to the intended data root and use safe artifact names rather than raw document IDs as paths. Configure input-size and processing-time limits from the measured corpus before running unfamiliar data.

ACL preservation is a provenance responsibility; current authorization enforcement belongs to the access/retrieval layer. Unknown ACLs in benchmark exports do not demonstrate production security. Future production releases require authenticated identity, permission-change handling, deletion handling, and verification that unauthorized content cannot reach models or users.

| Future source | Adapter responsibilities | Trigger |
|---|---|---|
| Native Confluence | Read the actual structured body, preserve page/section identities, ancestry, versions, and verified permission metadata. | A real connector is in scope. |
| PDFs/scans | Extract layout/OCR as needed; map elements to page positions and retained originals. | Such documents enter the agreed corpus. |
| Other office formats | Preserve the relevant native structure and source locations. | Required by an agreed source. |

All adapters should converge on the same document/block contract while retaining source-specific attributes. AWS deployment later must preserve versioned originals and outputs, bounded execution, durable outcomes, controlled publication, and access controls. Select actual services after capacity, latency, retention, recovery, and budget requirements are agreed; use the research report to evaluate parsing options then.

## 11. Verification and release gates

### Gate A — Contract review

Manually map one real document, including title/heading origin, a paragraph, and a table or list. Verify exact source locations. Agree on how uncertain labels appear before writing implementation code.

### Gate B — Representative fixtures

Start with the existing typical, table/code, long, and short examples. Add only examples needed to cover nested structure, Unicode/newlines, literal escapes, and malformed syntax. Expected output must be independently reviewed, not generated and accepted solely because the parser produced it.

### Gate C — Parser correctness

Test source reconstruction, span bounds, nested structures, heading-like text inside code, table delimiters, malformed input, and deterministic reruns. Include regression fixtures for actual bugs. These tests validate evidence integrity rather than mirroring internal function calls.

### Gate D — Batch and recovery

Run the full corpus; reconcile every outcome. Interrupt a run and resume it. Verify incomplete artifacts are invisible, unchanged artifacts are reused, and failed releases do not replace the active manifest. Review warning categories and sample their documents before accepting the release.

### Gate E — Retrieval handoff

Provide the chunker with a validated release, schema description, source-span conventions, and known limitations. Later compare parsing/chunking variants on fixed evaluation data, measuring retrieval and citation quality. Establish dataset revision parity and the benchmark protocol before claiming leaderboard comparability.

## 12. Delivery plan: very small PRs

Each row is an outcome, not a requirement to combine all related changes. Split a row further if the diff is difficult to explain. Do not begin the next implementation slice until the current behavior is understandable and reviewed.

| Order | Small deliverable | Review evidence |
|---|---|---|
| 1 | One manually annotated document and the minimal agreed contract. | Source beside proposed output; no parser code. |
| 2 | Bounded Markdown parser/dependency experiment on those examples. | Source-span accuracy and a concise dependency decision. |
| 3 | Single-document input validation and source identity. | Valid input, missing field, and unchanged bytes. |
| 4 | Paragraph/separator output with exact spans. | Complete reconstruction of one document. |
| 5 | Explicit headings and heading paths. | Nested/skipped levels and headings inside code handled correctly; add only required protective code recognition. |
| 6 | Complete code-block behavior. | Whitespace, language, literal escapes, and malformed fences. |
| 7 | Lists. | Nesting and continuation examples. |
| 8 | Tables. | Header/cell relationships and escaped delimiters. |
| 9 | Conservative plain-label candidates and warnings. | Ambiguous labels remain distinguishable from explicit headings. |
| 10 | Selected-document batch execution and outcome report. | Every selected record accounted for. |
| 11 | Versioned atomic artifact writes and reuse. | Interrupted write and identical rerun. |
| 12 | Release manifests and replacement/deletion semantics. | Incomplete release, rollback, and explicit deletion scenarios. |
| 13 | Full-corpus run and review report. | Quality gates, warnings, failures, runtime, and limitations. |

Production connector, AWS deployment, and chunking implementation require their own subsequent plans. They are interfaces considered here, not additional work bundled into parsing PRs.

## 13. Open decisions and definition of done

Resolve now through examples: exact block representation, separator convention, plain-label policy, and whether a Markdown dependency makes the implementation smaller and more reliable. Resolve after measurement: batch performance target and limits. Resolve before production: source inventory semantics, authorization freshness, retention, recovery objectives, and AWS service selection.

Parsing is complete for the current Confluence export when all selected records are accounted for, a validated release is reproducible, source content and anchors pass the stated gates, known structural limitations are documented, and a downstream chunker can consume the contract without reparsing raw text. This does not certify native Confluence support, production deployment, or benchmark rank.

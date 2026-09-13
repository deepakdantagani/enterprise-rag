# Enterprise Document Parsing for RAG

## Findings

Enterprise document parsing should produce a traceable representation of the source: ordered content, structural relationships, and locations that survive later chunking. The strongest common pattern in the reviewed documentation is to retain more than a flat string. AWS exposes layout and table relationships; Docling models document structure explicitly; Microsoft exposes structured content with location metadata. These are documented capabilities, rather than proof that every enterprise uses the same architecture. [1](https://docs.aws.amazon.com/textract/latest/dg/layoutresponse.html) [2](https://docling-project.github.io/docling/concepts/docling_document/) [3](https://learn.microsoft.com/en-us/azure/search/cognitive-search-skill-content-understanding)

For this project, the recommended next step is a small parser contract for the existing Confluence text exports. Preserve original content, identify ordered blocks, and attach exact local source locations. Review one document manually before implementing or processing the corpus.

| Proposed requirement | Research conclusion | Project decision proposed for review |
|---|---|---|
| Heading path in metadata and chunk text | Useful contextualization pattern; no evidence establishes it as universally the cheapest or best enhancement. | Preserve trustworthy headings as metadata; evaluate a title-and-heading prefix when chunking starts. |
| Precise citation anchors | Location information is supported by major parsing systems, but the available anchor depends on the source format. | Use raw-text line ranges now. Add native section or PDF coordinates only when available. |
| Source, version, timestamps, ACLs | Valuable provenance, but an ACL snapshot alone cannot ensure current authorization. | Retain verified source metadata; represent unavailable fields as unknown. |
| Parser version | Necessary for controlled reprocessing, but insufficient alone for reproducibility. | Track parser implementation and configuration separately from source and output-schema versions. |

This review covers official documentation and primary engineering publications consulted on September 12, 2026. Product capabilities can depend on service mode, API version, region, and configuration. Recommendations below are design judgments for this project, not claims that a particular schema is an industry standard.

## What enterprises demonstrably do

AWS describes Legal & General's production Docusort system using Textract and SageMaker to classify documents, extract information, and update backend systems. The case supports separating ingestion, extraction, and downstream business processing. It is a vendor-published customer case about document processing; it does not establish a RAG chunking strategy or a heading-path retrieval improvement. [4](https://aws.amazon.com/solutions/case-studies/legal-general/)

A September 2026 AWS technical article describes preprocessing complex utility bills with Textract before loading them into a Bedrock knowledge base. Its useful lesson is that a document's tabular relationships can require explicit extraction before retrieval works well. This is a technical walkthrough involving an unnamed customer, rather than an independently measured comparison across enterprises. [5](https://aws.amazon.com/blogs/machine-learning/customizing-your-knowledge-base-on-amazon-bedrock-for-large-and-complex-documents-using-amazon-textract/)

Neither source justifies applying OCR or generative parsing to every document. My recommendation is to route by the representation actually available: native structured content first, text parsing for text exports, and layout/OCR tools for documents whose information depends on visual structure.

## Separate parsing from its neighbors

The following separation is a proposed architecture. A managed service may combine several stages, but keeping their responsibilities explicit makes errors and reprocessing easier to reason about.

| Stage | Responsibility | Output |
|---|---|---|
| Ingestion | Capture source content, identity, and available source metadata. | Original document record. |
| Parsing | Identify content blocks, order, structure, and source locations. | A structured document representation. |
| Normalization | Produce a consistent representation without silently changing meaning. | Normalized content with mappings to the original. |
| Enrichment | Add derived descriptions or context when justified. | Separately identifiable derived content. |
| Chunking | Assemble retrieval units under a measured size and boundary policy. | Chunks referencing their source blocks. |
| Indexing and retrieval | Build searchable representations and enforce access policy. | Authorized evidence for answer generation. |

A parser should not invent a company's project taxonomy, decide a user's permissions, or silently convert generated summaries into source evidence. It should expose enough information for those later responsibilities without pretending missing information was recovered.

## Choose the parser from the source format

### Native Confluence

Confluence's Cloud Page API exposes page identity, title, space and parent identifiers, version information, and body representations including storage and Atlas Doc Format. The ancestors API supplies the ancestor chain. These are stronger sources for page relationships than guessing from filenames. The connector's ability to read a page establishes its own access, not every downstream user's access. [6](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/) [7](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-ancestors/)

Atlassian documents its Data Center storage format as XML with familiar HTML elements plus Confluence-specific constructs such as macros and resource references. This is evidence that stripping tags indiscriminately can discard meaning. It is Data Center documentation: a future Cloud connector must inspect the representation returned by the Cloud API rather than assume identical behavior for every macro. [8](https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html)

Proposed native-page handling: preserve heading levels, lists, tables, code, links, and attachment references from the source representation. Treat unsupported macros as explicit unresolved content. Keep page ancestry separate from headings inside the page, and retain source IDs so renamed pages remain identifiable.

### Our Confluence benchmark exports

The project currently has 5,189 local text records with `doc_id`, `source_type`, `source_path`, and `raw_content`. These came from the benchmark's GitHub v1.0.0 export; equivalence to the current Hugging Face revision has not been established. The local [corpus review](CONFLUENCE_REVIEW.md) records a heuristic scan showing headings, lists, tables, and code, with some literal escape sequences.

These records are already text. OCR cannot recover native page ancestry, actual heading levels, source permissions, or version history that the export omitted. Plain section labels can be recognized heuristically, but their original nesting may remain uncertain. A year in a title or a file modification time must not be promoted into an authoritative source update timestamp.

Proposed handling: retain raw text unchanged, detect explicit Markdown structure first, and mark any interpretation of plain headings as inferred. Do not globally replace literal `\\n` sequences: they may be content inside code or examples. Any normalization needs a reason and a mapping back to the original.

### PDFs, scans, and visual documents

Textract Layout returns typed blocks such as titles, section headers, lists, tables, and text, with geometry and relationships. Its output documents reading order, which matters for multi-column pages. A detected section header does not, by itself, establish a complete nested heading tree. [1](https://docs.aws.amazon.com/textract/latest/dg/layoutresponse.html)

Textract's table model includes cells, merged cells, column headers, titles, and other relationships. For retrieval over tables, my recommendation is to preserve those relationships and serialize them deliberately. Flattening all cells into an undifferentiated string can remove the association between a value and its header. [9](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html)

Bedrock Data Automation documents structured output with page and element information, reading order, bounding boxes, and text/Markdown/HTML representations. It also produces derived descriptions and summaries. For a project-owned representation, keep extracted text distinguishable from generated interpretation so citation checks can identify what the original document actually says. [10](https://docs.aws.amazon.com/bedrock/latest/userguide/bda-output-documents.html)

## AWS options and important distinctions

For customer-managed Bedrock knowledge bases, AWS documents a default text parser and advanced parsing through Bedrock Data Automation or foundation models. The default has no parsing usage charge; advanced parsing has additional usage-based costs. Choosing an advanced parser applies it to the data source's PDFs, including text-only PDFs. This makes source routing a practical cost decision. [11](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-advanced-parsing.html)

AWS also documents a separate Managed knowledge-base ingestion path using smart parsing or native multimodal embeddings. Explicit BDA/foundation-model parsing configuration from the customer-managed path does not transfer directly to this mode. Architecture decisions must name the service mode; instructions for one should not be mixed with the other. [12](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-customize-ingestion.html)

For customer-managed sources, the parsing strategy type cannot be changed after connection without creating a new data source, although some parameters within a strategy can be updated. That is a deployment constraint to consider later; it is not a reason to select AWS infrastructure before understanding the current text corpus. [13](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-data-source-customize-ingestion.html)

Bedrock's hierarchical chunking creates parent and child retrieval units using configured sizes. It is not equivalent to preserving the author's heading hierarchy. AWS also documents citation-related limitations when chunking is disabled. Therefore, turning on a chunking option should not be treated as proof that source structure and citation anchors have been retained. [14](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html)

## Other primary-source patterns

| System | Documented behavior | Implication for this project |
|---|---|---|
| Docling | A typed document representation with hierarchy, tables, and provenance/location information where available. | Use a structured representation as a design reference; installation is not yet necessary. [2](https://docling-project.github.io/docling/concepts/docling_document/) |
| Docling chunkers | Metadata-enriched serialization is separate from chunk generation; hybrid chunking uses document structure and token limits. | Keep original text separate from text prepared for embeddings. [15](https://docling-project.github.io/docling/concepts/chunking/) |
| Azure AI Search | Its layout-based example retains headings and content; current guidance directs new skillsets toward Content Understanding. | Check current APIs instead of copying an older tutorial unchanged. [16](https://learn.microsoft.com/en-us/azure/search/search-how-to-semantic-chunking) |
| Azure Content Understanding skill | Exposes location metadata and Markdown content. Stable functionality is distinct from opt-in preview semantic chunking and generated figure descriptions. | Pin the API contract and distinguish extraction from generated additions. [3](https://learn.microsoft.com/en-us/azure/search/cognitive-search-skill-content-understanding) |
| Databricks `ai_parse_document` | Returns typed elements with locations and confidence information; its version option controls output schema. | A schema version is not sufficient to identify a parser/model implementation. [17](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document) |

These sources demonstrate converging capabilities, not a measured winner. No comparative experiment on this project's Confluence exports was performed during this research.

## The four metadata requirements

### 1. Structural position

Keep three concepts separate: `page_ancestors` identifies containing pages, `heading_path` identifies sections inside a document, and a project association is an explicit business relationship. A space or parent page may help navigation without being equivalent to a project.

For trustworthy headings, the proposed chunk representation has both structured `heading_path` metadata and a separately constructed context prefix. Metadata supports filtering and navigation; the prefix makes context visible to the embedding or generation model. Preserve an unprefixed body so the contextual text does not contaminate source spans or quotations.

Docling explicitly supports metadata-enriched chunk serialization. Anthropic's contextual retrieval research studies a different technique: LLM-generated explanatory context prepended before embedding and lexical indexing. It supports testing context enrichment, but does not establish the effectiveness or cost ranking of heading-only prefixes. [15](https://docling-project.github.io/docling/concepts/chunking/) [18](https://www.anthropic.com/engineering/contextual-retrieval)

Pushback: “the single cheapest context enhancement” is too strong. Extracting an explicit Markdown heading is inexpensive, but reconstructing a missing hierarchy can require uncertain heuristics or model calls. Docling itself documents an optional heading-level inference stage and the harm of incorrect levels. For our exports, an unknown level is preferable to a confidently fabricated tree. [19](https://docling-project.github.io/docling/usage/heading_levels/)

### 2. Citation anchors

Use anchors appropriate to the actual source; do not require every record to have page numbers, timestamps, and section IDs simultaneously.

| Source | Proposed anchor | Important qualification |
|---|---|---|
| Current text export | Document ID, content hash, inclusive line range; optionally character offsets. | Refers to this exported version, not a verified native Confluence location. |
| Native Confluence | Page ID/version, source URL, verified section anchor or block location. | Do not generate a URL fragment and assume Confluence resolves it. |
| PDF | Document version, physical page index, bounding box or text span. | Printed page labels can differ from file page positions. |
| Audio/video transcript | Recording/version and start/end time. | Relevant only when the source supplies temporal alignment. |

The proposed convention for character spans is zero-based Unicode character offsets with an exclusive end; line ranges are one-based and inclusive. Choose and document one convention rather than mixing bytes and characters. For normalized text, retain a source mapping; for generated prefixes, record that they are derived and have no direct source span.

Precise anchors make evidence inspectable, but do not prove that an answer is supported. Evaluation must also check that the cited passage entails the claim. A document-level citation can be adequate for a short document or a whole-document claim; passage-level anchors are the stronger default for specific assertions.

### 3. Provenance and permissions

Proposed document provenance includes the source system, source document ID, raw content hash, available source version and update time, ingestion time, and a pointer to the retained original. These answer different questions. A content hash identifies captured bytes; it is not a substitute for a source system's version history.

An ACL snapshot is useful for audit and indexing, but permission changes can make it stale. ACL groups also may not capture individual grants, inherited restrictions, or other source-specific rules. Model the source authorization semantics explicitly when a real connector is introduced; do not derive access policy from document prose or an LLM.

AWS's Managed Confluence ACL documentation describes filtering with crawled ACLs followed by real-time verification of candidate documents against current permissions. It explicitly says this functionality does not authenticate users or constitute a security boundary: the application must authenticate users and provide verified identity. [20](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-confluence-acl.html)

By contrast, AWS's separate Confluence connector page warns that synced data can be retrieved by anyone with the relevant Bedrock retrieval permission, including data restricted at the source. These are materially different documented paths. A connector credential, successful ingestion, or generic claim of “Confluence integration” does not establish permission-safe retrieval. [21](https://docs.aws.amazon.com/bedrock/latest/userguide/confluence-data-source-connector.html)

For the benchmark records, source ACLs are unavailable. Represent this as unknown, not public or unrestricted. Benchmark retrieval experiments do not demonstrate production permission enforcement. In a future private deployment, authorization must cover all retrieved content sent to models and all evidence displayed to users, including cached results.

### 4. Parser version and selective reprocessing

Track source changes separately from processing changes. The proposed processing record contains parser name/version, configuration hash, output-schema version, and processing time. Add model identity, prompt/configuration, and dependency versions when those components actually exist. Do not add unused fields just to anticipate every possible implementation.

Some hosted interfaces version their output schema without pinning every underlying model behavior. Databricks' documentation illustrates this distinction. Retaining parser outputs and raw inputs makes comparison possible even when a service cannot promise byte-identical reruns. [17](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document)

Microsoft's enrichment-cache documentation describes reuse of unaffected stages and notes that changes inside custom code may require explicit invalidation. Its targeted reset documentation also distinguishes resetting processing state from running the indexer; some selective reset capabilities are preview. The general design lesson is dependency-aware reprocessing, not reliance on a version string alone. [22](https://learn.microsoft.com/en-us/azure/search/enrichment-cache-how-to-manage) [23](https://learn.microsoft.com/en-us/azure/search/search-howto-run-reset-indexers)

| Change | Proposed affected work |
|---|---|
| Raw content changes | Parse the new version; regenerate affected chunks and indexes. |
| Parser implementation/configuration changes | Select documents produced by the affected parser configuration; reparse and update dependent outputs. |
| Chunking changes | Reuse compatible parsed documents; rebuild chunks and dependent indexes. |
| Embedding model changes | Re-embed compatible chunk text; re-chunk only if constraints require it. |
| Permissions change | Refresh access state and invalidate affected cached access/results; content parsing may be unnecessary. |
| Document deleted | Remove retrieval eligibility and invalidate dependent results; follow the retention policy for raw artifacts. |

Selective reprocessing requires recording which outputs depend on which inputs. Publishing replacements must also retire obsolete chunks; otherwise new processing can leave old evidence searchable. These are future operational requirements, not implementation requested by this report.

## Proposed minimal representation

Keep the existing ingestion records as the original source. A separate parsed representation can add structure without changing `raw_content`. The following is a contract to review, not a request to build a database or populate every field immediately.

| Layer | Minimum useful information |
|---|---|
| Document | Existing ID/source/path/raw content; content hash; observed title; optional verified source metadata. |
| Parse result | Parser version/configuration identity; ordered blocks; warnings for unsupported or uncertain content. |
| Block | Type, exact source text/location, order, and available heading context; structural origin marked explicit or inferred. |
| Later chunk | Referenced blocks, unprefixed body, context-prefixed retrieval text, inherited provenance and source anchors. |

A table block should preserve its source and header/row relationships. A code block should preserve whitespace and a language label when explicitly present. Unsupported fragments should remain available with a warning rather than disappear silently. A normalized representation may evolve later; exact source preservation should not depend on that evolution.

### One actual local example

In [the typical preview](../data/confluence/preview/typical.md), the title appears on line 1, `Overview` on line 3, and a purpose paragraph on line 5. The manually proposed interpretation is:

| Field | Proposed value |
|---|---|
| Document title | Telemetry Normalization and Fidelity Acceptance Playbook for Enterprise Tenants |
| Block type | Paragraph |
| Source line range | 5–5, inclusive |
| Section label | Overview |
| Structural origin | Inferred from a plain-text label; no explicit Markdown level. |
| Native page ancestry / source ACL / source version | Unknown |

The paragraph should retain its exact raw text. Later, a chunk could receive the title and `Overview` as a context prefix, but that prefix must not change the paragraph's source location. This is a manually reviewed example, not output from an implemented parser.

## Evaluate before choosing a more complex parser

Start with a small reviewed set spanning explicit headings, plain labels, nested lists, tables, code, literal escapes, and unusually short content. Include documents with ambiguous structure, not only clean examples. Record the expected interpretation before comparing implementations.

| Check | What to inspect |
|---|---|
| Content preservation | Missing or duplicated meaningful text; all exclusions explained. |
| Reading order | Blocks appear in source order; table cells and list items retain relationships. |
| Structure | Explicit heading levels preserved; inferred levels assessed separately. |
| Table fidelity | Each sampled value remains associated with its correct headers. |
| Code fidelity | Indentation, punctuation, and literal escapes remain intact. |
| Anchor accuracy | Every sampled span resolves to the exact retained source version. |
| Reprocessing | Output identifies its source and parser configuration; affected documents can be selected. |

Only after parsing is reliable should retrieval experiments compare body-only chunks against title/heading-prefixed chunks while holding other choices fixed. Track retrieval quality, answer support, citation correctness, latency, and cost. Keep tuning examples separate from final evaluation wherever the benchmark protocol permits.

A parser's structural accuracy is an intermediate measure. It cannot by itself establish the project's top-10 benchmark objective, and Confluence-only experiments cannot establish whole-corpus performance. No benchmark improvement or leaderboard position is claimed here.

## Recommended next step

Review the proposed parsed representation of one existing Confluence document, including its headings, one table or list, and exact source anchors. Agree on how uncertain plain headings should be represented. Then implement only that reviewed parsing behavior in one small change; expand coverage when concrete examples require it.

The current evidence does not justify OCR, an LLM parser, a vector database, or AWS deployment for this step. The useful investment now is a faithful, inspectable representation that later chunking can consume.

## Sources

All web sources below were consulted on September 12, 2026. Unless a date is stated, no publication date is asserted; official documentation is mutable. Numbered links beside claims identify the supporting source.

1. AWS — [Textract Layout response](https://docs.aws.amazon.com/textract/latest/dg/layoutresponse.html).
2. Docling — [Document representation](https://docling-project.github.io/docling/concepts/docling_document/).
3. Microsoft — [Azure Content Understanding skill](https://learn.microsoft.com/en-us/azure/search/cognitive-search-skill-content-understanding), including stable versus preview API distinctions.
4. AWS — [Legal & General customer case study](https://aws.amazon.com/solutions/case-studies/legal-general/). Vendor-reported production example.
5. AWS Machine Learning Blog — [Complex-document preprocessing with Textract and Bedrock](https://aws.amazon.com/blogs/machine-learning/customizing-your-knowledge-base-on-amazon-bedrock-for-large-and-complex-documents-using-amazon-textract/), September 4, 2026. Technical walkthrough.
6. Atlassian — [Confluence Cloud REST API: Page](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/).
7. Atlassian — [Confluence Cloud REST API: Ancestors](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-ancestors/).
8. Atlassian — [Confluence storage format](https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html). Data Center documentation.
9. AWS — [Textract tables](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html).
10. AWS — [Bedrock Data Automation document output](https://docs.aws.amazon.com/bedrock/latest/userguide/bda-output-documents.html).
11. AWS — [Bedrock advanced parsing options](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-advanced-parsing.html).
12. AWS — [Managed knowledge-base ingestion customization](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-customize-ingestion.html).
13. AWS — [Customer-managed ingestion customization](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-data-source-customize-ingestion.html).
14. AWS — [Knowledge-base chunking](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html).
15. Docling — [Chunking and contextualization](https://docling-project.github.io/docling/concepts/chunking/).
16. Microsoft — [Structure-aware chunking with document layout](https://learn.microsoft.com/en-us/azure/search/search-how-to-semantic-chunking).
17. Databricks — [ai_parse_document](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document), updated September 11, 2026.
18. Anthropic — [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval), September 19, 2024. Provider research on generated context, not heading-only enrichment.
19. Docling — [Heading-level inference](https://docling-project.github.io/docling/usage/heading_levels/).
20. AWS — [Managed Confluence ACL behavior](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-confluence-acl.html).
21. AWS — [Confluence data-source connector](https://docs.aws.amazon.com/bedrock/latest/userguide/confluence-data-source-connector.html), including its retrieval-permission warning.
22. Microsoft — [Manage enrichment caching](https://learn.microsoft.com/en-us/azure/search/enrichment-cache-how-to-manage).
23. Microsoft — [Run and reset indexers](https://learn.microsoft.com/en-us/azure/search/search-howto-run-reset-indexers).

Local evidence: [Confluence corpus review](CONFLUENCE_REVIEW.md), [ingestion script](../scripts/ingest_confluence.py), and [typical document preview](../data/confluence/preview/typical.md). Local paths and line anchors describe the retained export, not independently verified live Confluence pages.

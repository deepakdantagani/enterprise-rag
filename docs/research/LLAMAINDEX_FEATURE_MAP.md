# LlamaIndex feature map

Every topic, subtopic and component named in the official LlamaIndex Python docs,
collected on 2026-09-25 from https://developers.llamaindex.ai.

**Where these lists come from:** sections 1-3 are the docs' own page tree
(`/api/list?path=/python/framework/`, 430 pages). Sections 4-18 list class names
found anywhere in the docs text (`/api/grep`) plus the headings of each "Module
Guides" page. Base classes and made-up example names are left out.

To refresh this file, re-run those two endpoints. `llms.txt` at the site root
describes the endpoints.

## 1. Getting Started (8 pages)

High-level concepts · Installation · How to read the docs · Starter tutorial (OpenAI) ·
Starter tutorial (local LLMs) · Video series · FAQ · Async Python

## 2. Learn (35 pages)

- **Using LLMs**
- **Agents:** building an agent, tools, state, streaming, human in the loop, multi-agent, structured output
- **RAG:** loading (LlamaHub, LlamaCloud), indexing, storing, querying
- **Structured extraction:** structured LLMs, structured prediction, low-level extraction, structured input
- **Tracing and debugging**
- **Evaluating:** cost analysis
- **Putting it all together:** agents, full-stack apps (Delphic), chatbots, Q&A patterns, terms and definitions, structured data
- **Privacy and security**

## 3. Use Cases (12 pages)

Agents · Chatbots · Fine-tuning · Multi-modal · Tables and charts · Prompting ·
Querying CSVs · Graph querying · Q&A (RAG) · Extraction · Text-to-SQL

## 4. Loading

- **SimpleDirectoryReader file types:** csv, docx, epub, hwp, ipynb, jpg/jpeg, mbox, md, mp3/mp4, pdf, png, ppt/pptm/pptx
- **Readers:** SimpleDirectory, PDF, PyMuPDF, Markdown, JSON, HWP, Image, ImageVisionLLM,
  PandasExcel, Unstructured, UpstageDocumentParse, SimpleWebPage, AsyncWebPage, WholeSite,
  FireCrawlWeb, ScrapflyWeb, ScrapyWeb, OlostepWeb, KnowledgeBaseWeb, Confluence, Notion,
  Slack, Discord, Telegram, GitHub, GoogleDocs, GoogleDrive, SharePoint, S3, GCS,
  AzStorageBlob, Minio, Database, Postgres, AlloyDB, SimpleMongo, ElasticSearch, Chroma,
  Qdrant, Pinecone, Wikipedia, Arxiv, YoutubeTranscript, Document360, FeishuWiki, Memos,
  StructuredData, Preprocess, LlamaParse, Docling, Deplot, and others
- **Documents and nodes:** customizing documents, customizing nodes, metadata
- **Ingestion pipeline:** transformations (TextSplitter, NodeParser, MetadataExtractor,
  embeddings), custom transformations, caching, document management

### Node parsers and chunkers

| Kind | Classes |
|---|---|
| File-based | `SimpleFileNodeParser`, `HTMLNodeParser`, `JSONNodeParser`, `MarkdownNodeParser` |
| Text splitters | `SentenceSplitter`, `TokenTextSplitter`, `CodeSplitter`, `SentenceWindowNodeParser`, `SemanticSplitterNodeParser`, `SemanticDoubleMergingSplitterNodeParser`, `TopicNodeParser`, `LangchainNodeParser` (includes `RecursiveCharacterTextSplitter`), `Chunker` / `RecursiveChunker`, `SimpleNodeParser` (legacy) |
| Element-based | `MarkdownElementNodeParser`, `UnstructuredElementNodeParser`, `SlideNodeParser` |
| Relation-based | `HierarchicalNodeParser` (used with `AutoMergingRetriever`) |

### Metadata extractors

`TitleExtractor`, `SummaryExtractor`, `QuestionsAnsweredExtractor`, `KeywordExtractor`,
`EntityExtractor`, `DocumentContextExtractor`, `MarvinMetadataExtractor`,
`MarvinEntityExtractor`, `EvaporateExtractor`, Pydantic extractor, custom extractors.

Property-graph extractors: `SimpleLLMPathExtractor`, `SchemaLLMPathExtractor`,
`DynamicLLMPathExtractor`, `ImplicitPathExtractor`.

## 5. Indexing

- **Indexes:** `VectorStoreIndex`, `SummaryIndex`, `TreeIndex`, `KeywordTableIndex`,
  `PropertyGraphIndex`, `KnowledgeGraphIndex`, `DocumentSummaryIndex`, `ObjectIndex`,
  SQL index, `MultiModalVectorStoreIndex`, `LlamaCloudIndex`
- **Other pages:** document management, metadata extraction, REBEL + knowledge graph

## 6. Storing

- **Vector stores:** 100+ documented (Simple, Chroma, Qdrant, Pinecone, Weaviate, Milvus,
  Postgres/pgvector, Elasticsearch, OpenSearch, FAISS, LanceDB, DuckDB, Redis, MongoDB Atlas,
  Neo4j, Azure AI Search, and more). Guides cover hybrid search, metadata filters, MMR,
  async, and using existing data.
- **Document stores:** Simple, MongoDB, Redis, Firestore, Couchbase, Tablestore, AlloyDB, Cloud SQL
- **Index stores:** Simple, MongoDB, Redis, Couchbase, Tablestore, AlloyDB, Cloud SQL
- **Chat stores:** Simple, Upstash, Redis, Azure, DynamoDB, Postgres, Tablestore, AlloyDB, Cloud SQL, YugabyteDB
- **Also:** key-value stores, graph stores, persisting and loading, customizing storage

## 7. Models

- **LLMs:** 91 integration pages. Also standalone use, customizing LLMs, local models.
- **Embeddings:** 49 integrations. Also batch size, ONNX/OpenVINO, custom embeddings.
- **Multi-modal:** OpenAI, Gemini, Anthropic, Replicate, CLIP, LLaVa and others; multi-modal RAG and eval
- **Prompts:** usage patterns
- **Rerankers:** see section 9

## 8. Retrievers

- **Built-in:** `VectorIndexRetriever`, `VectorIndexAutoRetriever`, `BM25Retriever`,
  `QueryFusionRetriever` (simple, reciprocal-rank, relative-score and distribution-based
  fusion), `AutoMergingRetriever`, `RecursiveRetriever`, `RouterRetriever`, Ensemble,
  `KnowledgeGraphRagRetriever`, `PGRetriever` / `VectorContextRetriever`, `NLSQLRetriever`,
  `DuckDBRetriever`, `LlamaCloudRetriever`, `LlamaCloudCompositeRetriever`
- **Managed and third-party:** Vectara, VertexAISearch, AmazonKnowledgeBases (Bedrock),
  VideoDB, You.com, Pathway, Activeloop DeepMemory, Koda, Galaxia, AlletraX10000
- **Retriever modes per index:**
  - Summary index: default / embedding / llm
  - Tree index: select_leaf / select_leaf_embedding / all_leaf / root
  - Keyword index: default / simple / rake
  - Knowledge graph index: keyword / embedding / hybrid
  - Document summary index: llm / embedding

## 9. Node postprocessors and rerankers

- **Filtering and reordering:** `SimilarityPostprocessor`, `KeywordNodePostprocessor`,
  `MetadataReplacementPostProcessor`, `LongContextReorder`, `SentenceEmbeddingOptimizer`,
  `LongLLMLinguaPostprocessor`
- **Time-based:** `FixedRecencyPostprocessor`, `EmbeddingRecencyPostprocessor`, `TimeWeightedPostprocessor`
- **PII:** `PIINodePostprocessor` (LLM version), `NERPIINodePostprocessor`
- **Neighbouring nodes:** `PrevNextNodePostprocessor`, `AutoPrevNextNodePostprocessor`
- **Rerankers:** `SentenceTransformerRerank`, `LLMRerank`, `CohereRerank`, `JinaRerank`,
  `VoyageAIRerank`, `MixedbreadAIRerank`, `NVIDIARerank`, `BedrockRerank`, `DashScopeRerank`,
  `ColbertRerank`, `ColPaliRerank`, `RankGPTRerank`, `RankLLMRerank`, FlagEmbedding,
  OpenVINO, AIMon, IBM watsonx

## 10. Response synthesis

- **Response modes:** `refine`, `compact` (default), `tree_summarize`, `simple_summarize`,
  `no_text`, `accumulate`, `compact_accumulate`
- **Also:** structured refine, custom prompts, `structured_answer_filtering`

## 11. Query engines

- **Basic:** `RetrieverQueryEngine`, `CustomQueryEngine`, `CitationQueryEngine`,
  `TransformQueryEngine` (HyDE and other query transforms), `MultiStepQueryEngine`,
  `SubQuestionQueryEngine`, `RouterQueryEngine`, `ToolRetrieverRouterQueryEngine`,
  Joint QA-Summary, Ensemble, Retry, `FLAREInstructQueryEngine`, `SimpleMultiModalQueryEngine`
- **Structured data:** `NLSQLTableQueryEngine`, `SQLTableRetrieverQueryEngine`,
  `SQLAutoVectorQueryEngine`, `SQLJoinQueryEngine`, PGVector SQL, DuckDB, `PandasQueryEngine`,
  Polars, `JSONQueryEngine`, `JSONalyzeQueryEngine`, `KnowledgeGraphQueryEngine`
- **Also:** streaming, usage patterns

## 12. Chat engines

`SimpleChatEngine`, `ContextChatEngine`, `CondenseQuestionChatEngine`,
`CondensePlusContextChatEngine`, `ReActChatEngine`

## 13. Routers and structured outputs

- **Selectors:** LLM single/multi selectors, Pydantic single/multi selectors. Routers can
  run as a query engine, a retriever, or standalone.
- **Output parsers:** Guardrails, LangChain
- **Pydantic programs:** text-completion, function-calling, Guidance, `DFProgram`, Evaporate

## 14. Agents

- **Agent types:** `FunctionAgent`, `ReActAgent`, `CodeActAgent`, `AgentWorkflow` (multi-agent), custom agents
- **Tools:** `FunctionTool`, `QueryEngineTool`, ToolSpecs, `OnDemandLoaderTool`, `LoadAndSearchToolSpec`, return-direct
- **Memory:**
  - Short-term and long-term memory
  - Memory blocks: `StaticMemoryBlock`, `FactExtractionMemoryBlock`, `VectorMemoryBlock`
  - Remote memory, custom chat stores, Mem0
  - Deprecated types: `ChatMemoryBuffer`, `ChatSummaryMemoryBuffer`, `VectorMemory`, `SimpleComposableMemory`

## 15. Workflows (18 pages, under LlamaAgents)

Branches and loops · Concurrency · Async · Streaming · State · Custom start/stop events ·
Resources · Unbound functions · Retries / error handling · Human in the loop ·
Durable workflows · DBOS · Drawing · Testing · Observability · Deploy as server · Python client

## 16. Evaluation

- **Response evaluators:** Faithfulness, Relevancy, Correctness, SemanticSimilarity,
  Guideline, PairwiseComparison, AnswerConsistency, AnswerSimilarity, Augmentation
  Accuracy/Precision, RetrievalPrecision, MultiModal Faithfulness/Relevancy
- **Retrieval evaluation:** `RetrieverEvaluator` (hit rate, MRR, and others)
- **Integrations:** DeepEval, UpTrain, RAGChecker, Cleanlab, Tonic Validate, TruLens
- **Datasets:** `LabelledRagDataset`, `LabelledEvaluatorDataset`, question generation, batch eval, cost analysis

## 17. Observability

- **Instrumentation:** Event, EventHandler, Span, SpanHandler, Dispatcher, custom events and spans
- **Callbacks:**
  - Event types: CHUNKING, NODE_PARSING, EMBEDDING, LLM, QUERY, RETRIEVE, SYNTHESIZE, TREE, SUB_QUESTION
  - Handlers: TokenCounting, LlamaDebug, Wandb, Aim, OpenInference, OpenAIFineTuning
- **Integrations:** OpenTelemetry, Arize Phoenix / LlamaTrace, SigNoz, W&B Weave, MLflow,
  OpenLLMetry, Langfuse, Literal AI, Opik, Argilla, Agenta, DeepEval, Maxim, HoneyHive,
  PromptLayer, Langtrace, OpenLIT, AgentOps

## 18. Other sections

- **MCP:** use MCP tools in LlamaIndex, or convert workflows and tools into MCP servers
- **Deploying:** agents, chat engines, query engines
- **Settings:** global `Settings`, migrating from ServiceContext
- **Community:** Llama Packs, full-stack projects, FAQ (7 pages), 12 integration guides
- **Integrations section:** 267 pages (LLMs 91, embeddings 49, retrievers 19, vector stores 108)
- **Changelog**

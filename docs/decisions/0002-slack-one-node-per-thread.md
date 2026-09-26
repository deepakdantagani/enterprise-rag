# 0002. Slack: one node per thread, no chunker

Date: 2026-09-26. Status: accepted.

## Decision

Embed every Slack thread whole, as the one node `SlackThreadParser` (SLACK-9) makes, with an
embedding model whose window is 8k tokens or more. No splitter, ours or LlamaIndex's. A
pass-through `EmbeddingWindowGuard` (SLACK-10) stops the run if any node is over the model's
window, because models truncate silently.

## Why

**Every thread fits.** Over all 285,597 nodes, counted with LlamaIndex's default tokenizer
(tiktoken `cl100k_base`) on what the embedder sees (metadata lines + text): p50 831, p90 1,254,
p99 1,714, max 4,143 tokens. An 8k window holds the largest thread with about 2x to spare, which
also covers a model whose tokenizer counts more tokens than `cl100k_base`.

**Every LlamaIndex option, measured** on all 285,597 nodes (tokens embedded = the embedding bill):

| | 1. one node per thread | 2. `SentenceSplitter(2048)` | 3. chunk references: parent + `SentenceSplitter(512)` children, `RecursiveRetriever` | 4. `HierarchicalNodeParser` + `AutoMergingRetriever` |
|---|---|---|---|---|
| custom code after the parser | none | an `id_func` | a wrapper + `id_func` | an `id_func` |
| cuts inside a message | 0 | 352 of 759 | 184,665 of 396,594 (children) | 184,665 of 396,594 (leaves) |
| what the LLM reads | the whole thread | one piece | the whole thread | leaves, or the thread when over half its leaves hit |
| vectors | 285,597 | 286,356 | 967,788 | 682,191 |
| tokens embedded | 246.0M | 246.0M | 502.0M | 256.0M |
| model window needed | ~4.2k+ (8k) | 2,048 | 8k if parents are embedded | 512 |
| turns on each piece | the thread's | wrong (whole thread) | wrong on children | wrong on leaves |
| ids stable across runs | yes (SLACK-9) | only with an `id_func` | only with an `id_func` | only with an `id_func` |

Also checked and not a fit: `TokenTextSplitter` (cuts like `SentenceSplitter`),
`MarkdownNodeParser`/`JSON`/`HTML`/element parsers (cut by markup, which chat has none of),
`SemanticSplitterNodeParser` and `SemanticDoubleMerging` (an embedding call per sentence, cuts
by meaning inside messages), `SentenceWindowNodeParser` (a node per sentence), `CodeSplitter`,
and the add-ons `TopicNodeParser`, `SlideNodeParser`, chonkie `Chunker`, `LangchainNodeParser`.
A custom `SlackMessageChunker` (cut between messages, balanced) was built and closed unmerged
(PR #29): with an 8k model it would never cut anything.

**What the literature says.** Slack guides treat the thread as the unit (Paragon; a
practitioner reports +5-6% for whole threads over 500-token chunks, without a published method;
Snyk moved away from size-based chunks to one Q&A per thread). Chunk-size studies disagree by
corpus: LlamaIndex found 1,024 best on a 10-K, a 2026 vendor benchmark found 512 best on papers,
TeleEmbedBench found 512 best on a small corpus and 2,048 on a large one. The known weakness of
one vector per long text is a single fact buried in it (LongEmbed; Jina's measurements favour
chunks for fact lookup and whole documents when the relevant information is spread out). Our
threads are short by those studies' standards (median 831 tokens), the benchmark scores whether
the gold thread is retrieved, and BM25 (required: 72.8% of threads carry an exact-match id)
finds buried identifiers at any node size.

## Consequences

- SLACK-11 picks an embedding model with an 8k+ window (local first: Qwen3-Embedding-0.6B, then
  bge-m3) and passes its window and tokenizer to the guard. With Ollama, `num_ctx` is set to the
  model's window.
- SLACK-12 tests the weakness directly: option 3 (chunk references) and late chunking against
  one node per thread on recall@20. If either wins, this decision is revisited.
- A model with a window under ~4.2k tokens brings a chunker back; the guard makes that loud.

## Sources

- [Paragon: ingesting Slack messages for RAG](https://www.useparagon.com/learn/guide-ingesting-slack-messages-for-rag/)
- [dev.to: Slack RAG accuracy with thread chunking](https://dev.to/criscmd/how-i-boosted-slack-rag-accuracy-by-5-6-with-smarter-chunking-1kf9)
- [Snyk: from Slack threads to structured knowledge](https://snyk.io/articles/from-slack-threads-to-structured-knowledge-implementing-rag-at-snyk/)
- [RAG chunking strategies: 2026 benchmark guide](https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/)
- [TeleEmbedBench](https://arxiv.org/pdf/2604.17778)
- [LongEmbed (EMNLP 2024)](https://arxiv.org/abs/2404.12096)
- [Jina: still need chunking with long-context models?](https://jina.ai/news/still-need-chunking-when-long-context-models-can-do-it-all/)
- [Jina: late chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- LlamaIndex docs: [node parser modules](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules), [recursive retriever + node references](https://developers.llamaindex.ai/python/framework/integrations/retrievers/recursive_retriever_nodes)

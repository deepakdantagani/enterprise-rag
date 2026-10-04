"""GEN-2a: first_documents and document_block, v4's ranked chunks as the documents the answerer reads.

The leaderboard scores answers (GEN-1), and the benchmark's own baseline (BM25 + GPT-5.4, 50.6)
gives its LLM the top 10 whole documents. v4 ranks chunks, and a long document matches in
several places: for qst_0001 ("default size limits for file uploads … multipart upload support
on the OpenAI-compatible API endpoints") the gold document's three chunks rank #1, #2 and #8,
and 14 chunks hold 10 documents. So a document ranks where its best chunk ranks, repeats are
skipped, and the chunk texts are dropped: the answerer reads each whole document (GEN-2b).
All 470 saved questions reach 10 documents, within 11 chunks at the median and 27 at most.

    >>> document_block(1, "dsid_a", "Q3 budget", "Priya approved it.")
    '--- Document 1 (ID: dsid_a) ---\\nTitle: Q3 budget\\n\\nPriya approved it.'
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from llama_index.core import PromptTemplate
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.llms import LLM
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from pydantic import PrivateAttr

TOP_DOCUMENTS = 10  # as the benchmark's baseline answerer
ANSWERER = "gemma4:26b"  # GEN-2d: local on Ollama, $0; thinking off for the base case (a later story compares)
DEEPSEEK_ANSWERER = "deepseek-v4-pro"  # GEN-12a: paid, about $5.60 per 500 questions off-peak
CONTEXT_WINDOW = 40_960  # the largest top 10 is ~35K tokens; Ollama's default window would cut it silently

# GEN-2d: the first prompt, kept as it was scored. 62.11 on our judge (GEN-9e): 339 of 500 correct.
# Rule 6 made 156 answers open with "The documents do not say", 94 of them before a right answer.
ANSWER_PROMPT_V1 = PromptTemplate(
    "You are a precise assistant answering questions about Redwood Inference, using documents\n"
    "from the company's internal systems (Slack, Gmail, Linear, Jira, Confluence, GitHub,\n"
    "Google Drive, HubSpot, meeting transcripts). The documents come from an imperfect search:\n"
    "many will be irrelevant, and some may be outdated or duplicated.\n\n"
    "Rules:\n"
    "1. Use only the documents. Never add facts from outside them or guess.\n"
    "2. Answer every part of the question. Copy exact values as written: names, numbers,\n"
    "   units, dates, versions, IDs, flags and config keys.\n"
    "3. Respect every qualifier in the question (team, customer, date, version, environment).\n"
    "   Ignore documents that match the topic but fail a qualifier.\n"
    "4. If the question asks for a list or \"all\", include every matching item from all documents.\n"
    "5. If documents disagree, give each value, say where each comes from, and say which is\n"
    "   newer or more authoritative.\n"
    "6. If the documents do not contain the answer, say so plainly in the first sentence\n"
    "   (\"The documents do not say ...\"). You may then add closely related facts you did find.\n"
    "7. Include every detail the documents give that answers the question. No preamble,\n"
    "   no citations, no markdown.\n\n"
    "## Documents\n{context_str}\n\n## Question\n{query_str}\n\n## Answer\n")

# GEN-10a: rules 3, 5, 6 and 7 changed from v1; each change comes from a judged v1 answer (story table).
ANSWER_PROMPT_V2 = PromptTemplate(
    "You are a precise assistant answering questions about Redwood Inference, using documents\n"
    "from the company's internal systems (Slack, Gmail, Linear, Jira, Confluence, GitHub,\n"
    "Google Drive, HubSpot, meeting transcripts). The documents come from an imperfect search:\n"
    "most are irrelevant to the question, and some may be outdated or duplicated.\n\n"
    "Rules:\n"
    "1. Use only the documents. Never add facts from outside them or guess.\n"
    "2. Answer every part of the question. Copy exact values as written: names, numbers,\n"
    "   units, dates, versions, IDs, flags and config keys.\n"
    "3. First find the one document (or few) the question is about. The question often describes\n"
    "   it in other words (\"a big retail tenant\" may be \"Acme Retail\"): a document that fits the\n"
    "   description is the right one even if the wording differs. Answer from it, and leave out\n"
    "   every document about a different customer, project, meeting or system.\n"
    "4. If the question asks for a list or \"all\", include every matching item from all documents.\n"
    "5. Report a disagreement only when two documents describe the same thing and give different\n"
    "   values. Then give each value, where it comes from, and which is newer or more\n"
    "   authoritative. Different values for different things are not a disagreement.\n"
    "6. Start with the answer itself. Write \"The documents do not say ...\" only when no document\n"
    "   answers the question, and never before an answer you then give.\n"
    "7. Include every detail the documents give that answers the question. Write plain sentences:\n"
    "   no preamble, no bullet points, no bold, no headings, and never refer to a document by its\n"
    "   number (\"Document 3\"); name its source instead (\"the go-live runbook\").\n\n"
    "## Documents\n{context_str}\n\n## Question\n{query_str}\n\n## Answer\n")

ANSWER_PROMPT = ANSWER_PROMPT_V2  # the prompt answer_engine uses


def first_documents(ranked: Sequence[NodeWithScore], count: int = TOP_DOCUMENTS) -> List[str]:
    """The first `count` distinct documents of ranked chunks, each where its best chunk ranks."""
    return list(dict.fromkeys(chunk.node.ref_doc_id for chunk in ranked))[:count]  # unique, first-seen order


def documents_by_id(parquet_path: Union[str, Path], doc_ids: Sequence[str]) -> Dict[str, Tuple[str, str]]:
    """GEN-2b: title and whole content of each asked document, read in one pass over the corpus.

    The corpus is one 1.4 GB row group, so every read scans it all (1.2 s): ask once for every
    question's documents (4,532 over the 470), not once per question. 4 ids each name two
    different documents (a benchmark data slip): the second text follows the first.
    """
    import pyarrow.parquet as pq
    rows = pq.read_table(parquet_path, columns=["doc_id", "title", "content"],
                         filters=[("doc_id", "in", list(doc_ids))]).to_pylist()
    documents: Dict[str, Tuple[str, str]] = {}
    for row in rows:
        title = (row["title"] or "").strip()
        if row["doc_id"] in documents:
            first_title, first_content = documents[row["doc_id"]]
            documents[row["doc_id"]] = (first_title, f"{first_content}\n\n{title}\n\n{row['content']}")
        else:
            documents[row["doc_id"]] = (title, row["content"] or "")
    return documents


def document_block(number: int, doc_id: str, title: str, content: str) -> str:
    """One document as the benchmark's baseline shows it to its LLM (src/utils/retrieval.py)."""
    return f"--- Document {number} (ID: {doc_id}) ---\nTitle: {title}\n\n{content}"


class FullDocuments(BaseNodePostprocessor):
    """GEN-2c: ranked chunks in, one node per document out (the first 10), holding the whole document.

    The chunks only choose the documents and their order; the text comes from `documents`
    (documents_by_id, loaded once for every question). The doc_id stays in metadata for the
    answer file's document_ids but is hidden from the LLM, which already reads it in the block.
    """
    count: int = TOP_DOCUMENTS
    _documents: Dict[str, Tuple[str, str]] = PrivateAttr()
    _corpus: Optional[Path] = PrivateAttr()

    def __init__(self, documents: Dict[str, Tuple[str, str]], count: int = TOP_DOCUMENTS,
                 corpus: Optional[Union[str, Path]] = None) -> None:
        super().__init__(count=count)
        self._documents, self._corpus = documents, Path(corpus) if corpus else None

    def _postprocess_nodes(self, nodes: List[NodeWithScore],
                           query_bundle: Optional[QueryBundle] = None) -> List[NodeWithScore]:
        doc_ids = first_documents(nodes, self.count)
        missing = [doc_id for doc_id in doc_ids if doc_id not in self._documents]
        if missing and self._corpus:  # GEN-8a: a live question can land anywhere in the corpus
            self._documents.update(documents_by_id(self._corpus, missing))
        sources = {}  # GEN-8b: each document's source system, from its best chunk, for the ask page
        for chunk in nodes:
            sources.setdefault(chunk.node.ref_doc_id, chunk.node.metadata.get("source_type"))
        return [NodeWithScore(node=TextNode(id_=doc_id, text=document_block(number, doc_id, *self._documents[doc_id]),
                                            metadata={"doc_id": doc_id, "source_type": sources.get(doc_id)},
                                            excluded_llm_metadata_keys=["doc_id", "source_type"]),
                              score=1.0)
                for number, doc_id in enumerate(doc_ids, 1)]


def answerer_llm(model: str = ANSWERER) -> LLM:
    from llama_index.llms.ollama import Ollama
    return Ollama(model=model, temperature=0, thinking=False, context_window=CONTEXT_WINDOW, request_timeout=600)


def deepseek_answerer_llm(api_key: Optional[str] = None) -> LLM:
    """GEN-12a: the same documents and prompt on a stronger model; temperature 0 and thinking off, as the local one.

    gemma4:26b answers 69.0% correctly with recall@10 0.834; 68 of its 155 wrong answers read every
    gold document. The key is DEEPSEEK_API_KEY in .env. The model reads 1M tokens; 128K is set so
    LlamaIndex never splits a top 10 (the largest is ~35K tokens) into two calls.
    """
    from llama_index.llms.deepseek import DeepSeek
    return DeepSeek(model=DEEPSEEK_ANSWERER, api_key=api_key, temperature=0.0, max_tokens=2_048, context_window=128_000,
                    additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}})


def answer_engine(retriever: BaseRetriever, llm: LLM, documents: Dict[str, Tuple[str, str]],
                  reranker: Optional[BaseNodePostprocessor] = None,
                  corpus: Optional[Union[str, Path]] = None, streaming: bool = False) -> RetrieverQueryEngine:
    """GEN-2d: retriever → (GEN-8a: reranker) → FullDocuments → compact synthesizer with ANSWER_PROMPT."""
    steps = ([reranker] if reranker else []) + [FullDocuments(documents, corpus=corpus)]
    return RetrieverQueryEngine.from_args(retriever, llm=llm, text_qa_template=ANSWER_PROMPT, node_postprocessors=steps,
                                          streaming=streaming)  # GEN-8b: the ask page shows the answer as it is written


def answer_row(engine: RetrieverQueryEngine, question_id: str, question: str) -> dict:
    """GEN-2d: one line of the leaderboard's answer file."""
    response = engine.query(question)
    return {"question_id": question_id, "answer": str(response).strip(),
            "document_ids": [found.node.metadata["doc_id"] for found in response.source_nodes]}


def save_answers(engine: RetrieverQueryEngine, questions: Sequence, out_path: Union[str, Path]) -> int:
    """GEN-2e: answer every question not yet in `out_path`, one flushed line each; returns how many this call.

    500 local answers take ~1.5 h, so a crash or a re-run never asks the LLM again for a finished
    question (the pattern of rerank_saved and save_completions).
    """
    out_path = Path(out_path)
    done = {json.loads(line)["question_id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    answered = 0
    with out_path.open("a") as out:
        for question in questions:
            if question.question_id in done:
                continue
            out.write(json.dumps(answer_row(engine, question.question_id, question.text)) + "\n")
            out.flush()
            answered += 1
    return answered


V4_COLLECTION = "titles__voyage_4_lite__bm25"  # GEN-8a: dense voyage-4-lite + BM25 over the same titled chunks
LIVE_LISTS, LIVE_CANDIDATES = 200, 100  # as the saved v4 run: RRF over 200-deep lists, the top 100 reranked
RERANKER = "rerank-3-lite"


def live_retriever(client, embed_model) -> BaseRetriever:
    """GEN-8a: v4's search for any question; on qst_0001 it returns the saved top 100, in order."""
    from llama_index.core.llms import MockLLM
    from llama_index.core.retrievers import QueryFusionRetriever
    from pipeline.eval.hybrid import dense_retriever, hybrid_store, sparse_retriever
    store = hybrid_store(client, V4_COLLECTION)
    return QueryFusionRetriever([dense_retriever(store, embed_model, LIVE_LISTS), sparse_retriever(store, LIVE_LISTS)],
                                mode="reciprocal_rerank", similarity_top_k=LIVE_CANDIDATES, num_queries=1,
                                llm=MockLLM(), use_async=False)  # MockLLM: no LLM rewrites the question


def live_reranker(api_key: Optional[str] = None) -> BaseNodePostprocessor:
    """GEN-8a: rerank-3-lite over all 100 candidates (LlamaIndex's VoyageAIRerank)."""
    from llama_index.postprocessor.voyageai_rerank import VoyageAIRerank
    return VoyageAIRerank(model=RERANKER, api_key=api_key, top_n=LIVE_CANDIDATES)

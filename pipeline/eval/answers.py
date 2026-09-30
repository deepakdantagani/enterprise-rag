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
CONTEXT_WINDOW = 40_960  # the largest top 10 is ~35K tokens; Ollama's default window would cut it silently

ANSWER_PROMPT = PromptTemplate(  # GEN-2d: each rule comes from the judge prompts or a question type (story table)
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

    def __init__(self, documents: Dict[str, Tuple[str, str]], count: int = TOP_DOCUMENTS) -> None:
        super().__init__(count=count)
        self._documents = documents

    def _postprocess_nodes(self, nodes: List[NodeWithScore],
                           query_bundle: Optional[QueryBundle] = None) -> List[NodeWithScore]:
        return [NodeWithScore(node=TextNode(id_=doc_id, text=document_block(number, doc_id, *self._documents[doc_id]),
                                            metadata={"doc_id": doc_id}, excluded_llm_metadata_keys=["doc_id"]),
                              score=1.0)
                for number, doc_id in enumerate(first_documents(nodes, self.count), 1)]


def answerer_llm(model: str = ANSWERER) -> LLM:
    from llama_index.llms.ollama import Ollama
    return Ollama(model=model, temperature=0, thinking=False, context_window=CONTEXT_WINDOW, request_timeout=600)


def answer_engine(retriever: BaseRetriever, llm: LLM, documents: Dict[str, Tuple[str, str]]) -> RetrieverQueryEngine:
    """GEN-2d: retriever → FullDocuments → compact synthesizer with ANSWER_PROMPT."""
    return RetrieverQueryEngine.from_args(retriever, llm=llm, text_qa_template=ANSWER_PROMPT,
                                          node_postprocessors=[FullDocuments(documents)])


def answer_row(engine: RetrieverQueryEngine, question_id: str, question: str) -> dict:
    """GEN-2d: one line of the leaderboard's answer file."""
    response = engine.query(question)
    return {"question_id": question_id, "answer": str(response).strip(),
            "document_ids": [found.node.metadata["doc_id"] for found in response.source_nodes]}

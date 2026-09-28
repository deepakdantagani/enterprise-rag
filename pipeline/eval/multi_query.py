"""RET-7: multi_query_retriever, v1's hybrid search for the question plus 3 LLM-written queries, fused by RRF.

v2 (RET-6) finds 526 of the 741 relevant documents in its top 10, but 161 never reach v1's top 50,
so no reranker can lift them: qst_0436 ("Across Redwood's Go, Python, and TypeScript SDKs, which
SDK has the most customer-reported auth-related bug reports …") needs 10 documents and v1 finds 1.
LlamaIndex's QueryFusionRetriever, which v1 already runs with num_queries=1, asks an LLM for more
queries when num_queries > 1: its default prompt and num_queries=4 (the question + 3), each query
searched dense and BM25, all 8 lists fused by RRF. Nothing here replaces it; the planner is the
local gemma4:26b on Ollama ($0, ~0.6 s a question; qwen3:30b ignored thinking=False and wrote
its reasoning into the answer, 12–31 s a question). Each question is planned once and saved, so
scoring replays the same queries (the scorer retrieves every question once per k).

    >>> llm = SavedCompletions({query_prompt("Who approved the Q3 budget?"): "Q3 budget approval\\nbudget sign-off"})
    >>> llm.complete(query_prompt("Who approved the Q3 budget?")).text.split("\\n")
    ['Q3 budget approval', 'budget sign-off']
"""
import json
from pathlib import Path
from typing import Dict, List, Sequence, Union

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM, CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import QUERY_GEN_PROMPT
from llama_index.vector_stores.qdrant import QdrantVectorStore
from pydantic import PrivateAttr

from pipeline.eval.hybrid import RETRIEVED_CHUNKS, dense_retriever, sparse_retriever
from pipeline.eval.questions import Question

PLANNER = "gemma4:26b"  # local on Ollama
NUM_QUERIES = 4  # LlamaIndex's default: the question itself + 3 generated
# RET-7b: LlamaIndex's default asks for "related" queries and gemma4 made them generic (qst_0064's
# "upcoming external pen test" became "standard timeframe for fixing ... vulnerabilities")
PERSPECTIVE_PROMPT = (  # the RAG-Fusion / LangChain MultiQueryRetriever style
    "Generate {num_queries} different versions of the user question to retrieve relevant documents "
    "from a vector database. Vary the wording and perspective. One per line, no numbering.\n\n"
    "Question: {query}\n")
KEEP_DETAILS_PROMPT = (  # keep the question's key information, change only the wording
    "Generate {num_queries} search queries to find the documents that answer the question below in a "
    "company's internal knowledge base.\n"
    "Keep every name, product, project, team, customer, number, date and quoted term from the question "
    "in every query.\n"
    "Change only the wording: use synonyms and the terms the documents are likely to use.\n"
    "Each query must be self-contained. One per line, no numbering.\n\n"
    "Question: {query}\nQueries:\n")


def planner_llm(model: str = PLANNER) -> LLM:
    from llama_index.llms.ollama import Ollama
    return Ollama(model=model, temperature=0, thinking=False, request_timeout=300)


def query_prompt(question: str, prompt: str = QUERY_GEN_PROMPT, num_queries: int = NUM_QUERIES) -> str:
    """The exact prompt QueryFusionRetriever sends for `question`."""
    return prompt.format(num_queries=num_queries - 1, query=question)


class SavedCompletions(CustomLLM):
    """The planner's saved answer to each prompt, so a re-score replays the same queries for $0."""
    _saved: Dict[str, str] = PrivateAttr()

    def __init__(self, saved: Dict[str, str]) -> None:
        super().__init__()
        self._saved = saved

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="saved-completions")

    def complete(self, prompt: str, formatted: bool = False, **kwargs) -> CompletionResponse:
        if prompt not in self._saved:
            raise KeyError(f"no saved completion for {prompt!r}")
        return CompletionResponse(text=self._saved[prompt])

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs):
        raise NotImplementedError("saved completions are replayed whole")


def save_completions(questions: Sequence[Question], llm: LLM, out_path: Union[str, Path],
                     prompt: str = QUERY_GEN_PROMPT) -> int:
    """Plan every question not yet in `out_path`; returns how many were planned by this call."""
    out_path = Path(out_path)
    done = {json.loads(line)["question_id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    planned = 0
    with out_path.open("a") as out:
        for question in questions:
            if question.question_id in done:
                continue
            sent = query_prompt(question.text, prompt)
            out.write(json.dumps({"question_id": question.question_id, "prompt": sent,
                                  "completion": llm.complete(sent).text}) + "\n")
            out.flush()
            planned += 1
    return planned


def saved_completions(path: Union[str, Path]) -> SavedCompletions:
    rows = (json.loads(line) for line in Path(path).read_text().splitlines())
    return SavedCompletions({row["prompt"]: row["completion"] for row in rows})


def multi_query_retriever(store: QdrantVectorStore, embed_model: BaseEmbedding, llm: LLM,
                          top_k: int = RETRIEVED_CHUNKS, prompt: str = QUERY_GEN_PROMPT) -> QueryFusionRetriever:
    return QueryFusionRetriever([dense_retriever(store, embed_model, top_k), sparse_retriever(store, top_k)],
                                llm=llm, query_gen_prompt=prompt, mode="reciprocal_rerank", similarity_top_k=top_k, num_queries=NUM_QUERIES,
                                use_async=False)  # as v1: sync calls stay sync; the scorer uses aretrieve


def generated_queries(retriever: QueryFusionRetriever, question: str) -> List[str]:
    """The queries the retriever adds to `question`, parsed by LlamaIndex itself (so they can be embedded first)."""
    return [bundle.query_str for bundle in retriever._get_queries(question)]

import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata  # noqa: E402
from llama_index.core.schema import MetadataMode, NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode  # noqa: E402

from pipeline.eval import answers  # noqa: E402
from pipeline.eval.answers import (FullDocuments, answer_engine, answer_row, answerer_llm, document_block,  # noqa: E402
                                   documents_by_id, first_documents, live_reranker, live_retriever, save_answers)
from pipeline.eval.questions import Question  # noqa: E402
from pipeline.eval.rerank import ReplayRetriever  # noqa: E402

CORPUS = ROOT / "data/_full/documents.parquet"
RERANK = ROOT / "data/_index/rerank"
CANDIDATES = RERANK / "lite_titles_top100_candidates.jsonl"
V4_ORDER = RERANK / "lite-titles-top100-rerank-3-lite.jsonl"
QUESTION_VECTORS = ROOT / "data/_index/question_embeddings/voyage-4.jsonl"


def chunk_of(doc_id):
    return NodeWithScore(node=TextNode(text="chunk", relationships={
        NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)}), score=1.0)


class FirstDocuments(unittest.TestCase):
    def test_keeps_the_first_ten_distinct_documents_in_rank_order(self):
        ranked = [chunk_of(f"dsid_{n}") for n in [3, 3, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]]
        self.assertEqual(first_documents(ranked), ["dsid_3", "dsid_0", "dsid_1", "dsid_2", "dsid_4",
                                                   "dsid_5", "dsid_6", "dsid_7", "dsid_8", "dsid_9"])

    def test_a_document_ranks_where_its_best_chunk_ranks(self):
        ranked = [chunk_of("dsid_b"), chunk_of("dsid_a"), chunk_of("dsid_b"), chunk_of("dsid_a")]
        self.assertEqual(first_documents(ranked), ["dsid_b", "dsid_a"])

    def test_fewer_documents_than_ten_keeps_them_all(self):
        self.assertEqual(first_documents([chunk_of("dsid_1"), chunk_of("dsid_2")]), ["dsid_1", "dsid_2"])

    def test_no_chunks_gives_no_documents(self):
        self.assertEqual(first_documents([]), [])


class DocumentBlock(unittest.TestCase):
    def test_the_benchmark_baseline_layout(self):
        self.assertEqual(document_block(2, "dsid_a", "Q3 budget", "Priya approved it."),
                         "--- Document 2 (ID: dsid_a) ---\nTitle: Q3 budget\n\nPriya approved it.")


def parquet_of(rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    folder = tempfile.mkdtemp()
    path = Path(folder) / "documents.parquet"
    pq.write_table(pa.Table.from_pylist([{"doc_id": d, "title": t, "content": c} for d, t, c in rows]), path)
    return path


class DocumentsById(unittest.TestCase):
    def test_returns_only_the_asked_documents(self):
        path = parquet_of([("a", "A", "about a"), ("b", "B", "about b"), ("c", "C", "about c")])
        self.assertEqual(documents_by_id(path, ["a", "c"]), {"a": ("A", "about a"), "c": ("C", "about c")})

    def test_titles_lose_surrounding_spaces(self):
        self.assertEqual(documents_by_id(parquet_of([("a", "  A  ", "about a")]), ["a"]), {"a": ("A", "about a")})

    def test_an_id_used_by_two_documents_shows_both_texts(self):
        path = parquet_of([("a", "First", "one"), ("a", "Second", "two")])
        self.assertEqual(documents_by_id(path, ["a"]), {"a": ("First", "one\n\nSecond\n\ntwo")})

    def test_an_unknown_id_is_left_out(self):
        self.assertEqual(documents_by_id(parquet_of([("a", "A", "about a")]), ["zzz"]), {})


DOCUMENTS = {"dsid_2": ("Title 2", "Content 2"), "dsid_5": ("Title 5", "Content 5")}


class FullDocumentsPostprocessor(unittest.TestCase):
    def setUp(self):
        self.kept = FullDocuments(DOCUMENTS).postprocess_nodes([chunk_of("dsid_5"), chunk_of("dsid_5"), chunk_of("dsid_2")])

    def test_each_document_becomes_one_numbered_node_with_its_whole_text(self):
        self.assertEqual([found.node.text for found in self.kept],
                         ["--- Document 1 (ID: dsid_5) ---\nTitle: Title 5\n\nContent 5",
                          "--- Document 2 (ID: dsid_2) ---\nTitle: Title 2\n\nContent 2"])

    def test_each_node_is_its_document_id_and_keeps_it_in_metadata(self):
        self.assertEqual([(found.node.node_id, found.node.metadata["doc_id"]) for found in self.kept],
                         [("dsid_5", "dsid_5"), ("dsid_2", "dsid_2")])

    def test_the_llm_sees_the_block_without_a_doc_id_line(self):
        self.assertEqual(self.kept[0].node.get_content(metadata_mode=MetadataMode.LLM),
                         "--- Document 1 (ID: dsid_5) ---\nTitle: Title 5\n\nContent 5")

    def test_a_document_that_was_not_loaded_fails_loudly(self):
        with self.assertRaises(KeyError):
            FullDocuments(DOCUMENTS).postprocess_nodes([chunk_of("dsid_missing")])


class RecordingLLM(CustomLLM):
    """Answers with a fixed text and keeps every prompt it was sent."""
    prompts: list = []

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="recording", context_window=40_960)

    def complete(self, prompt, formatted=False, **kwargs):
        self.prompts.append(prompt)
        return CompletionResponse(text=" Priya approved the Q3 budget. ")

    def stream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError


class AnswerRow(unittest.TestCase):
    def setUp(self):
        saved = {"question_id": "q1", "question": "Who approved the Q3 budget?",
                 "candidates": [{"node_id": "c1", "ref_doc_id": "dsid_5", "text": "chunk"},
                                {"node_id": "c2", "ref_doc_id": "dsid_2", "text": "chunk"}]}
        self.llm = RecordingLLM(prompts=[])
        self.engine = answer_engine(ReplayRetriever({"Who approved the Q3 budget?": saved}), self.llm, DOCUMENTS)

    def test_the_row_is_the_leaderboard_answer_format(self):
        self.assertEqual(answer_row(self.engine, "q1", "Who approved the Q3 budget?"),
                         {"question_id": "q1", "answer": "Priya approved the Q3 budget.",
                          "document_ids": ["dsid_5", "dsid_2"]})

    def test_the_llm_gets_the_rules_the_whole_documents_and_the_question_in_one_call(self):
        answer_row(self.engine, "q1", "Who approved the Q3 budget?")
        prompt, = self.llm.prompts
        self.assertIn("1. Use only the documents.", prompt)
        self.assertIn("7. Include every detail the documents give that answers the question.", prompt)
        self.assertIn("6. Start with the answer itself.", prompt)  # GEN-10a: the engine answers with v2
        self.assertIn("--- Document 1 (ID: dsid_5) ---\nTitle: Title 5\n\nContent 5", prompt)
        self.assertNotIn("doc_id:", prompt)
        self.assertIn("## Question\nWho approved the Q3 budget?\n\n## Answer", prompt)

    def test_the_answerer_is_local_deterministic_and_has_room_for_the_largest_top_ten(self):
        llm = answerer_llm()
        self.assertEqual((llm.model, llm.temperature, llm.thinking, llm.context_window),
                         ("gemma4:26b", 0.0, False, 40_960))


class DeepSeekAnswerer(unittest.TestCase):
    """GEN-12a: the same documents and prompt on a stronger model; only the model differs from gemma4:26b."""

    def setUp(self):
        self.llm = answers.deepseek_answerer_llm(api_key="test-key")

    def test_it_is_deepseek_v4_pro_deterministic_like_the_local_answerer(self):
        self.assertEqual((self.llm.model, self.llm.temperature), ("deepseek-v4-pro", 0.0))

    def test_thinking_is_off_as_for_the_local_answerer(self):
        self.assertEqual(self.llm.additional_kwargs, {"extra_body": {"thinking": {"type": "disabled"}}})

    def test_the_largest_top_ten_fits_in_one_call_with_room_for_a_long_answer(self):
        self.assertEqual((self.llm.context_window, self.llm.max_tokens), (128_000, 2_048))

    def test_the_key_comes_from_the_environment(self):
        with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "from-env"}):
            self.assertEqual(answers.deepseek_answerer_llm().api_key, "from-env")

    def test_the_answer_run_answers_with_it(self):
        from pipeline.eval import answer_run
        self.assertIs(answer_run.ANSWERER_LLM, answers.deepseek_answerer_llm)


class AnswerPromptVersions(unittest.TestCase):
    """GEN-10a: v1 is kept as scored (62.11); v2 changes rules 3, 5, 6 and 7."""
    v1, v2 = answers.ANSWER_PROMPT_V1.template, answers.ANSWER_PROMPT_V2.template

    def test_v1_is_kept_as_it_was_scored(self):
        self.assertIn('6. If the documents do not contain the answer, say so plainly in the first sentence', self.v1)
        self.assertIn("no citations, no markdown.", self.v1)

    def test_the_current_prompt_is_v2(self):
        self.assertIs(answers.ANSWER_PROMPT, answers.ANSWER_PROMPT_V2)

    def test_v2_answers_first_and_refuses_only_when_nothing_answers(self):
        self.assertIn('6. Start with the answer itself. Write "The documents do not say ..." only when no document\n'
                      "   answers the question, and never before an answer you then give.", self.v2)
        self.assertNotIn("say so plainly in the first sentence", self.v2)

    def test_v2_picks_the_document_the_question_describes(self):
        self.assertIn("3. First find the one document (or few) the question is about.", self.v2)
        self.assertIn("5. Report a disagreement only when two documents describe the same thing", self.v2)

    def test_v2_names_every_banned_format(self):
        self.assertIn("no preamble, no bullet points, no bold, no headings", self.v2)
        self.assertIn('never refer to a document by its\n   number ("Document 3")', self.v2)

    def test_rules_1_2_and_4_and_the_layout_are_unchanged(self):
        for kept in ("1. Use only the documents. Never add facts from outside them or guess.",
                     "2. Answer every part of the question. Copy exact values as written: names, numbers,",
                     '4. If the question asks for a list or "all", include every matching item from all documents.',
                     "## Documents\n{context_str}\n\n## Question\n{query_str}\n\n## Answer\n"):
            self.assertIn(kept, self.v1)
            self.assertIn(kept, self.v2)

    def test_v2_answers_go_to_their_own_file_so_the_v1_answers_are_kept(self):
        from pipeline.eval import answer_run
        self.assertEqual(answer_run.ANSWERS.name, "v4-deepseek-v4-pro-v2.jsonl")  # GEN-12a: gemma's stay in v4-gemma4-v2.jsonl


class SaveAnswers(unittest.TestCase):
    def setUp(self):
        saved = {"question_id": "q", "question": "Q?", "candidates": [{"node_id": "c1", "ref_doc_id": "dsid_5", "text": "chunk"}]}
        self.llm = RecordingLLM(prompts=[])
        self.engine = answer_engine(ReplayRetriever({"Who?": dict(saved, question="Who?"), "When?": dict(saved, question="When?")}),
                                    self.llm, DOCUMENTS)
        self.questions = [Question("q1", "simple", (), "Who?", ()), Question("q2", "simple", (), "When?", ())]
        self.out = Path(tempfile.mkdtemp()) / "answers.jsonl"
        self.out.write_text(json.dumps({"question_id": "q1", "answer": "old", "document_ids": []}) + "\n")

    def test_resume_answers_only_the_questions_not_saved(self):
        self.assertEqual(save_answers(self.engine, self.questions, self.out), 1)
        self.assertEqual(len(self.llm.prompts), 1)
        self.assertEqual([json.loads(line) for line in self.out.read_text().splitlines()],
                         [{"question_id": "q1", "answer": "old", "document_ids": []},
                          {"question_id": "q2", "answer": "Priya approved the Q3 budget.", "document_ids": ["dsid_5"]}])

    def test_nothing_new_calls_no_llm(self):
        save_answers(self.engine, self.questions, self.out)
        self.llm.prompts.clear()
        self.assertEqual(save_answers(self.engine, self.questions, self.out), 0)
        self.assertEqual(self.llm.prompts, [])


class LiveParts(unittest.TestCase):
    def test_full_documents_reads_a_document_it_was_not_given_from_the_corpus(self):
        corpus = parquet_of([("dsid_new", "New", "fresh text")])
        kept = FullDocuments(dict(DOCUMENTS), corpus=corpus).postprocess_nodes([chunk_of("dsid_new"), chunk_of("dsid_2")])
        self.assertEqual([found.node.text for found in kept],
                         ["--- Document 1 (ID: dsid_new) ---\nTitle: New\n\nfresh text",
                          "--- Document 2 (ID: dsid_2) ---\nTitle: Title 2\n\nContent 2"])

    def test_the_live_reranker_is_rerank_3_lite_over_all_100_candidates(self):
        reranker = live_reranker(api_key="not-a-real-key")
        self.assertEqual((reranker.model, reranker.top_n), ("rerank-3-lite", 100))

    def test_the_reranker_runs_before_full_documents(self):
        engine = answer_engine(ReplayRetriever({}), RecordingLLM(prompts=[]), DOCUMENTS,
                               reranker=live_reranker(api_key="not-a-real-key"))
        self.assertEqual([type(step).__name__ for step in engine._node_postprocessors],
                         ["VoyageAIRerank", "FullDocuments"])


@unittest.skipUnless(QUESTION_VECTORS.is_file() and CANDIDATES.is_file(), "saved question vectors or candidates absent")
class RealLiveRetriever(unittest.TestCase):
    def test_live_top_100_for_qst_0001_is_the_saved_top_100(self):
        from qdrant_client import QdrantClient
        from pipeline.eval.embedders import saved_query_embeddings
        client = QdrantClient(url="http://localhost:6333", timeout=600)
        try:
            client.get_collections()
        except Exception:
            self.skipTest("Qdrant not running")
        saved = json.loads(CANDIDATES.read_text().splitlines()[0])
        found = live_retriever(client, saved_query_embeddings(QUESTION_VECTORS)).retrieve(saved["question"])
        self.assertEqual([chunk.node.node_id for chunk in found], [c["node_id"] for c in saved["candidates"]])


@unittest.skipUnless(CORPUS.is_file() and CANDIDATES.is_file() and V4_ORDER.is_file(), "corpus or saved v4 reranks absent")
class RealFullDocuments(unittest.TestCase):
    def test_qst_0009_gets_the_whole_edgepath_thread_first(self):
        from pipeline.eval.rerank import replay_retriever
        chunks = replay_retriever(CANDIDATES, V4_ORDER).retrieve(
            "In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose "
            "instead of matching the competitor's 50 percent first-year discount and migration credit?")
        kept = FullDocuments(documents_by_id(CORPUS, first_documents(chunks))).postprocess_nodes(chunks)
        self.assertEqual((len(kept), kept[0].node.node_id), (10, "dsid_85deb10a652742baaf28af6149600001"))
        self.assertIn("CloudOrbit (the incumbent) is offering a 50% discount", kept[0].node.text)


@unittest.skipUnless(CORPUS.is_file(), "corpus absent")
class RealDocuments(unittest.TestCase):
    def test_the_gold_document_of_qst_0001_is_read_whole(self):
        title, content = documents_by_id(CORPUS, ["dsid_ae068ee4aa9640159427cd941bef0238"])[
            "dsid_ae068ee4aa9640159427cd941bef0238"]
        self.assertTrue(title.startswith("add multipart/form-data handling"))
        self.assertEqual(len(content), 5120)

    def test_the_signal_peak_id_shows_both_of_its_documents(self):
        title, content = documents_by_id(CORPUS, ["dsid_8a0c5430bac64f8da21c2cee5a7f4df5"])[
            "dsid_8a0c5430bac64f8da21c2cee5a7f4df5"]
        self.assertEqual(title, "Signal Peak Logistics — Account Brief (Renewal + Expansion) — 2026-03-18")
        self.assertEqual(len(content), 1534 + len("\n\nSignal Peak Logistics\n\n") + 3645)


@unittest.skipUnless(CANDIDATES.is_file() and V4_ORDER.is_file(), "saved v4 reranks absent")
class RealTopTen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.eval.rerank import replay_retriever
        cls.retriever = replay_retriever(CANDIDATES, V4_ORDER)
        cls.questions = [json.loads(line)["question"] for line in CANDIDATES.read_text().splitlines()]

    def test_qst_0001_gets_ten_documents_with_its_gold_document_first(self):
        doc_ids = first_documents(self.retriever.retrieve(self.questions[0]))
        self.assertEqual((len(doc_ids), doc_ids[0]), (10, "dsid_ae068ee4aa9640159427cd941bef0238"))

    def test_every_question_reaches_ten_documents(self):
        counts = [len(first_documents(self.retriever.retrieve(question))) for question in self.questions]
        self.assertEqual((len(counts), set(counts)), (500, {10}))  # GEN-4: 470 + the 30 with no expected documents


class Doctests(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(answers).failed, 0)


if __name__ == "__main__":
    unittest.main()

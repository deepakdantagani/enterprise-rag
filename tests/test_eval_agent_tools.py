"""RET-10a: search_snippets, ranked chunks as one block per document, the search tool's text.

Run: uv run python -m unittest tests.test_eval_agent_tools
"""
import doctest
import json
import sys
import unittest
from pathlib import Path

from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import agent_tools as agent_tools_module  # noqa: E402
from pipeline.eval.agent_tools import search_snippets  # noqa: E402

RERANK = ROOT / "data/_index/rerank"
CANDIDATES, ORDER = RERANK / "lite_titles_top200_candidates.jsonl", RERANK / "lite-titles-top200-rerank-3-lite.jsonl"
DOCUMENTS, QUESTIONS = ROOT / "data/_full/documents.parquet", ROOT / "data/_full/questions.jsonl"

TITLES = {"dsid_a": ("github", "Multipart PR"), "dsid_b": ("slack", "docs"), "dsid_c": ("gmail", "Re: limits")}


def chunk(doc_id: str, text: str) -> NodeWithScore:
    node = TextNode(text=text, relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=doc_id)})
    return NodeWithScore(node=node, score=1.0)


RANKED = [chunk("dsid_a", "Multipart PR\n\ndescription: default 10MiB per file"), chunk("dsid_a", "review: raise to 25MB?"),
          chunk("dsid_b", "sam: the example 415s"), chunk("dsid_a", "release notes: limits documented"),
          chunk("dsid_c", "Re: limits\nagreed on 50MiB total")]


class SearchSnippets(unittest.TestCase):
    def test_chunks_of_one_document_become_one_block_with_its_two_best_chunks_and_the_match_count(self):
        text = search_snippets(RANKED, TITLES)
        self.assertEqual(text.count("dsid_a"), 1)
        self.assertIn("[1] Multipart PR | github | dsid_a | 3 chunks matched, 2 shown", text)
        self.assertIn("(rank 1) description: default 10MiB per file", text)
        self.assertIn("(rank 2) review: raise to 25MB?", text)
        self.assertNotIn("release notes", text)

    def test_documents_come_in_best_chunk_order_and_are_cut_at_the_limit(self):
        ranked = [chunk(f"dsid_{n}", f"text {n}") for n in range(12)]
        text = search_snippets(ranked, {f"dsid_{n}": ("slack", f"t{n}") for n in range(12)}, documents=10)
        self.assertEqual([line.split("]")[0] + "]" for line in text.splitlines() if line.startswith("[")],
                         [f"[{n}]" for n in range(1, 11)])
        self.assertNotIn("dsid_10", text)

    def test_a_source_filter_keeps_only_that_source_before_the_cut(self):
        text = search_snippets(RANKED, TITLES, source="gmail")
        self.assertEqual([line for line in text.splitlines() if line.startswith("[")], ["[1] Re: limits | gmail | dsid_c | 1 chunk matched, 1 shown"])
        mixed = [chunk("dsid_s", "slack chunk")] * 10 + [chunk("dsid_c", "Re: limits\nlate gmail chunk")]
        self.assertIn("[1] Re: limits | gmail | dsid_c", search_snippets(mixed, {**TITLES, "dsid_s": ("slack", "general")}, source="gmail", documents=1))

    def test_read_and_seen_documents_are_marked(self):
        text = search_snippets(RANKED, TITLES, read={"dsid_a"}, seen={"dsid_b"})
        self.assertIn("dsid_a | 3 chunks matched, 2 shown (read)", text)
        self.assertIn("dsid_b | 1 chunk matched, 1 shown (seen)", text)

    def test_the_title_line_is_stripped_and_a_snippet_is_cut_with_an_ellipsis(self):
        text = search_snippets([chunk("dsid_c", "Re: limits\n" + "x" * 500)], TITLES, snippet_chars=400)
        self.assertIn("(rank 1) " + "x" * 400 + "…", text)
        self.assertNotIn("x" * 401, text)

    def test_a_title_that_is_only_a_word_prefix_is_not_stripped(self):
        titles = {"dsid_i": ("slack", "incidents")}
        self.assertIn("(rank 1) incidents-bot: SEV2 Pager", search_snippets([chunk("dsid_i", "incidents-bot: SEV2 Pager")], titles))
        self.assertIn("(rank 1) alice: paged", search_snippets([chunk("dsid_i", "incidents\nalice: paged")], titles))

    def test_newlines_inside_a_snippet_become_spaces(self):
        self.assertIn("(rank 1) line one line two", search_snippets([chunk("dsid_b", "line one\nline two")], TITLES))

    def test_an_unknown_document_id_gets_a_placeholder_title_never_an_exception(self):
        self.assertIn("[1] (no title) | ? | dsid_zz | 1 chunk matched, 1 shown", search_snippets([chunk("dsid_zz", "t")], TITLES))

    def test_no_chunks_gives_the_no_results_line(self):
        self.assertEqual(search_snippets([], TITLES), "No documents matched.")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(agent_tools_module).failed, 0)


@unittest.skipUnless(all(p.is_file() for p in (CANDIDATES, ORDER, DOCUMENTS, QUESTIONS)), "needs data/_index/rerank and data/_full")
class RealCorpus(unittest.TestCase):
    def test_qst_0001_gives_10_blocks_with_the_gold_document_first_in_under_2500_tokens(self):
        from pipeline.eval.rerank import replay_retriever
        from pipeline.eval.titles import document_titles
        table = document_titles(DOCUMENTS)
        titles = {d: (s, t) for d, s, t in zip(*(table.column(c).to_pylist() for c in ("doc_id", "source_type", "title")))}
        question = next(q for q in map(json.loads, QUESTIONS.read_text().splitlines()) if q["question_id"] == "qst_0001")
        ranked = replay_retriever(CANDIDATES, ORDER).retrieve(question["question"])
        text = search_snippets(ranked, titles)
        blocks = [line for line in text.splitlines() if line.startswith("[")]
        self.assertEqual(len(blocks), 10)
        self.assertIn(f"[1] add multipart/form-data handling, strict content-type validation, and payload limit enforcement for API "
                      f"tool/file inputs | github | {question['expected_doc_ids'][0]} | 3 chunks matched, 2 shown", blocks[0])
        self.assertLess(len(text) / 4, 2500)


if __name__ == "__main__":
    unittest.main()

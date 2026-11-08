"""RET-9a: titles_like, every document whose title contains a pattern, capped, with the total.

Run: uv run python -m unittest tests.test_eval_titles
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import titles as titles_module  # noqa: E402
from pipeline.eval.titles import TitleList, document_titles, titles_like  # noqa: E402

DOCUMENTS = ROOT / "data/_full/documents.parquet"
QUESTIONS = ROOT / "data/_full/questions.jsonl"

ROWS = [
    {"doc_id": "dsid_a", "source_type": "confluence", "title": "Postmortem: Streaming stalls", "content": "x"},
    {"doc_id": "dsid_b", "source_type": "confluence", "title": "P0 Incident Postmortem: Control plane outage", "content": "x"},
    {"doc_id": "dsid_c", "source_type": "confluence", "title": "Runbook: Deploy perf-canary", "content": "x"},
    {"doc_id": "dsid_d", "source_type": "slack", "title": "postmortems", "content": "x"},
    {"doc_id": "dsid_e", "source_type": "slack", "title": "", "content": "x"},
    {"doc_id": "dsid_a", "source_type": "hubspot", "title": "Postmortem Partners Inc", "content": "x"},
]
TABLE = pa.Table.from_pylist(ROWS)


class TitlesLike(unittest.TestCase):
    def test_rows_whose_title_contains_the_pattern_in_title_order_with_the_total(self):
        self.assertEqual(titles_like(TABLE, "confluence", "Postmortem"),
                         TitleList(rows=[("confluence", "dsid_b", "P0 Incident Postmortem: Control plane outage"),
                                         ("confluence", "dsid_a", "Postmortem: Streaming stalls")], total=2))

    def test_the_match_ignores_case(self):
        self.assertEqual(titles_like(TABLE, "slack", "POSTMORTEM").rows, [("slack", "dsid_d", "postmortems")])

    def test_more_matches_than_the_limit_returns_the_first_limit_rows_and_the_full_total(self):
        result = titles_like(TABLE, "confluence", "Postmortem", limit=1)
        self.assertEqual((len(result.rows), result.total), (1, 2))
        self.assertEqual(result.rows[0][1], "dsid_b")

    def test_no_source_searches_every_source_and_each_row_keeps_its_own(self):
        rows = titles_like(TABLE, None, "postmortem").rows
        self.assertEqual([(source, doc_id) for source, doc_id, _ in rows],
                         [("confluence", "dsid_b"), ("hubspot", "dsid_a"), ("confluence", "dsid_a"), ("slack", "dsid_d")])

    def test_a_pattern_nothing_matches_gives_no_rows_and_total_zero(self):
        self.assertEqual(titles_like(TABLE, "confluence", "Gmail digest"), TitleList(rows=[], total=0))

    def test_an_empty_pattern_matches_every_title_but_the_empty_one(self):
        self.assertEqual(titles_like(TABLE, "slack", "").total, 1)  # "postmortems" yes, "" no

    def test_document_titles_loads_only_the_three_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "documents.parquet"
            pq.write_table(TABLE, path)
            table = document_titles(path)
        self.assertEqual((table.column_names, table.num_rows), (["doc_id", "source_type", "title"], 6))

    def test_doctests(self):
        self.assertEqual(doctest.testmod(titles_module).failed, 0)


@unittest.skipUnless(DOCUMENTS.is_file() and QUESTIONS.is_file(), "needs data/_full")
class RealCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = document_titles(DOCUMENTS)
        cls.questions = {row["question_id"]: row for row in map(json.loads, QUESTIONS.read_text().splitlines())}

    def test_confluence_postmortem_lists_73_titles_holding_all_9_gold_pages_of_qst_0437(self):
        result = titles_like(self.table, "confluence", "Postmortem")
        listed = {doc_id for _, doc_id, _ in result.rows}
        gold = set(self.questions["qst_0437"]["expected_doc_ids"])
        self.assertEqual((result.total, len(result.rows), len(gold), gold <= listed), (73, 73, 9, True))

    def test_a_slack_channel_is_cut_at_the_limit_with_the_full_total(self):
        result = titles_like(self.table, "slack", "eng-security")
        self.assertEqual((len(result.rows), result.total), (200, 12432))


if __name__ == "__main__":
    unittest.main()

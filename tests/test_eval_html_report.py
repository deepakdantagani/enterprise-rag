"""EVAL-5c: html_report, one self-contained page comparing the retrieval steps per source.

Run: uv run python -m unittest tests.test_eval_html_report
"""
import doctest
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import html_report as html_report_module  # noqa: E402
from pipeline.eval.html_report import REPORT_STEPS, VERSIONS, V1_STEPS, html_report  # noqa: E402

RUNS = ROOT / "docs/eval/runs"
RRF_EXACT = RUNS / "2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf-exact"


def means(value):
    return {"hit_rate": value, "recall": value, "precision": value / 10, "mrr": value, "ndcg": value}


def write_metrics(runs_dir, run_name, value):
    rows = [{"group": group, "k": k, "questions": questions, "means": means(value + k / 1000)}
            for group, questions in (("overall", 4), ("type:basic", 4), ("source:slack", 1), ("source:jira", 3))
            for k in (5, 10, 20)]
    (runs_dir / run_name).mkdir(parents=True)
    (runs_dir / run_name / "metrics.json").write_text(json.dumps({"config": {}, "rows": rows}))


def embedded(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


class HtmlReport(unittest.TestCase):
    def setUp(self):
        self.runs_dir = Path(tempfile.mkdtemp())
        write_metrics(self.runs_dir, "run-dense", 0.5)
        write_metrics(self.runs_dir, "run-rrf", 0.7)
        self.page = html_report([("1. Dense", "exact", "run-dense"), ("2. RRF", "exact", "run-rrf")],
                                self.runs_dir, "Retrieval",
                                versions=[("v0", "run-dense", "dense"), ("v1", "run-rrf", "hybrid")])
        self.data = embedded(self.page)

    def test_buttons_are_all_then_sources_by_question_count(self):
        self.assertEqual([(g["id"], g["name"], g["questions"]) for g in self.data["groups"]],
                         [("overall", "All", 4), ("source:jira", "jira", 3), ("source:slack", "slack", 1)])

    def test_every_step_is_embedded_for_overall_and_each_source_at_every_k(self):
        for group in ("overall", "source:jira", "source:slack"):
            self.assertEqual(list(self.data["tables"][group]), ["10", "5", "20"])
            rows = self.data["tables"][group]["10"]
            self.assertEqual([(row["step"], row["search"], row["values"]["recall"]) for row in rows],
                             [("1. Dense", "exact", 0.51), ("2. RRF", "exact", 0.71)])

    def test_the_best_value_in_each_column_is_marked(self):
        rows = self.data["tables"]["overall"]["5"]
        self.assertEqual((rows[0]["best"], rows[1]["best"]), ([], ["hit_rate", "recall", "precision", "mrr", "ndcg"]))
        self.assertIn(".best", self.page)

    def test_the_page_is_self_contained_apart_from_its_fonts(self):
        self.assertNotIn("<script src", self.page)
        self.assertEqual(set(re.findall(r'href="(https?://[^/"]+)', self.page)), {"https://fonts.googleapis.com"})
        self.assertIn("<title>Retrieval</title>", self.page)

    def test_both_themes_follow_the_viewer_and_the_explicit_toggle(self):
        self.assertIn(':root:not([data-theme="light"])', self.page)
        self.assertIn(':root[data-theme="dark"]', self.page)
        self.assertIn("color-scheme: dark", self.page)

    def test_versions_carry_recall_and_mrr_at_10_and_the_gain_over_the_previous(self):
        self.assertEqual(self.data["versions"], [
            {"name": "v0", "about": "dense", "recall": 0.51, "mrr": 0.51, "gain": None},
            {"name": "v1", "about": "hybrid", "recall": 0.71, "mrr": 0.71, "gain": 0.2}])

    def test_a_missing_run_names_it(self):
        with self.assertRaisesRegex(FileNotFoundError, "run-absent"):
            html_report([("x", "exact", "run-absent")], self.runs_dir, "t")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(html_report_module).failed, 0)


@unittest.skipUnless(RRF_EXACT.is_dir(), "needs docs/eval/runs/...-hybrid-rrf-exact")
class RealV1Report(unittest.TestCase):
    def test_rrf_v1_exact_overall_recall_at_10_is_0_722(self):
        rows = embedded(html_report(V1_STEPS, RUNS, "v1"))["tables"]["overall"]["10"]
        rrf = [row for row in rows if (row["step"], row["search"]) == ("4. Hybrid RRF (v1)", "exact")]
        self.assertEqual(rrf[0]["values"]["recall"], 0.722)
        self.assertEqual(len(rows), 7)

    def test_v4_is_v3_on_voyage_4_lite_at_recall_0_834(self):
        versions = embedded(html_report(V1_STEPS, RUNS, "v4", versions=VERSIONS))["versions"]
        self.assertEqual([(v["name"], v["recall"], v["gain"]) for v in versions],
                         [("v0", 0.626, None), ("v1", 0.722, 0.096), ("v2", 0.8, 0.078), ("v3", 0.845, 0.045),
                          ("v4", 0.834, -0.011)])

    def test_the_report_is_the_voyage_4_lite_chain_with_v4_last(self):
        rows = embedded(html_report(REPORT_STEPS, RUNS, "v4"))["tables"]["overall"]["10"]
        self.assertEqual([(row["step"], row["values"]["recall"]) for row in rows],
                         [("1. Dense only (voyage-4-lite, titles)", 0.606), ("2. BM25 with titles", 0.688),
                          ("3. Hybrid RRF, both with titles", 0.732), ("4. Top 100 + rerank-3-lite (v4)", 0.834)])


if __name__ == "__main__":
    unittest.main()

"""EVAL-2b: metrics_report, mean metrics per (group, k): overall, per question type, per source.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import report as report_module  # noqa: E402
from pipeline.eval.questions import Question, load_questions  # noqa: E402
from pipeline.eval.report import ReportRow, Scored, metrics_report, write_run  # noqa: E402

QUESTIONS = ROOT / "data/_full/questions.jsonl"
SLACK_BASIC = Question("q1", "basic", ("slack",), "…", ("dsid_a",))
SLACK_AND_JIRA = Question("q2", "semantic", ("slack", "jira"), "…", ("dsid_b", "dsid_c"))


def rows_by_group(rows):
    return {(row.group, row.k): row for row in rows}


class MetricsReport(unittest.TestCase):
    def test_overall_is_the_mean_over_questions(self):
        rows = rows_by_group(metrics_report([Scored(SLACK_BASIC, 10, {"recall": 1.0}),
                                             Scored(SLACK_AND_JIRA, 10, {"recall": 0.5})]))
        self.assertEqual(rows[("overall", 10)], ReportRow("overall", 10, 2, {"recall": 0.75}))

    def test_a_question_counts_in_every_one_of_its_sources(self):
        rows = rows_by_group(metrics_report([Scored(SLACK_BASIC, 10, {"recall": 1.0}),
                                             Scored(SLACK_AND_JIRA, 10, {"recall": 0.5})]))
        self.assertEqual(rows[("source:slack", 10)].questions, 2)
        self.assertEqual(rows[("source:jira", 10)], ReportRow("source:jira", 10, 1, {"recall": 0.5}))

    def test_each_question_type_is_a_group(self):
        rows = rows_by_group(metrics_report([Scored(SLACK_BASIC, 10, {"recall": 1.0}),
                                             Scored(SLACK_AND_JIRA, 10, {"recall": 0.5})]))
        self.assertEqual(rows[("type:semantic", 10)].means, {"recall": 0.5})

    def test_each_k_is_its_own_row(self):
        rows = rows_by_group(metrics_report([Scored(SLACK_BASIC, 5, {"recall": 0.0}),
                                             Scored(SLACK_BASIC, 20, {"recall": 1.0})]))
        self.assertEqual((rows[("overall", 5)].means, rows[("overall", 20)].means), ({"recall": 0.0}, {"recall": 1.0}))

    def test_overall_comes_first(self):
        self.assertEqual(metrics_report([Scored(SLACK_BASIC, 10, {"recall": 1.0})])[0].group, "overall")

    def test_doctests(self):
        self.assertEqual(doctest.testmod(report_module).failed, 0)


SCORED = [Scored(SLACK_BASIC, 10, {"recall": 1.0, "mrr": 1.0}), Scored(SLACK_AND_JIRA, 10, {"recall": 0.5, "mrr": 0.25}),
          Scored(SLACK_BASIC, 5, {"recall": 0.0, "mrr": 0.0})]


class WriteRun(unittest.TestCase):
    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp()) / "2026-09-27-hybrid-rrf-exact"
        write_run(self.run_dir, {"mode": "hybrid-rrf", "exact": True}, SCORED)

    def test_metrics_json_holds_the_config_and_the_report_rows(self):
        written = json.loads((self.run_dir / "metrics.json").read_text())
        self.assertEqual(written["config"], {"mode": "hybrid-rrf", "exact": True})
        self.assertEqual(written["rows"], [row._asdict() for row in metrics_report(SCORED)])

    def test_scored_jsonl_has_one_line_per_question_and_k(self):
        lines = [json.loads(line) for line in (self.run_dir / "scored.jsonl").read_text().splitlines()]
        self.assertEqual([(line["question_id"], line["k"]) for line in lines], [("q1", 10), ("q2", 10), ("q1", 5)])
        self.assertEqual(lines[1], {"question_id": "q2", "question_type": "semantic", "source_types": ["slack", "jira"],
                                    "k": 10, "metrics": {"recall": 0.5, "mrr": 0.25}})

    def test_a_rerun_overwrites_instead_of_appending(self):
        write_run(self.run_dir, {"mode": "hybrid-rrf", "exact": True}, SCORED[:1])
        self.assertEqual(len((self.run_dir / "scored.jsonl").read_text().splitlines()), 1)


@unittest.skipUnless(QUESTIONS.is_file(), "needs data/_full/questions.jsonl")
class RealGroupSizes(unittest.TestCase):
    def test_group_sizes_on_the_470_questions(self):
        scored = [Scored(question, 10, {"recall": 0.0}) for question in load_questions(QUESTIONS).questions]
        sizes = {row.group: row.questions for row in metrics_report(scored)}
        self.assertEqual(sizes["overall"], 470)
        self.assertEqual({group: n for group, n in sizes.items() if group.startswith("source:")}, {
            "source:confluence": 114, "source:jira": 100, "source:slack": 79, "source:github": 60,
            "source:google_drive": 60, "source:linear": 58, "source:gmail": 55, "source:hubspot": 34,
            "source:fireflies": 25})
        self.assertEqual(sizes["type:basic"], 175)
        self.assertEqual(sum(n for group, n in sizes.items() if group.startswith("type:")), 470)


if __name__ == "__main__":
    unittest.main()

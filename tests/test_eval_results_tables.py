"""EVAL-5b: results_tables, the results.md tables generated from the run files, never typed.

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
from pipeline.eval import results_tables as tables_module  # noqa: E402
from pipeline.eval.results_tables import V1_STEPS, Step, replace_generated, results_tables  # noqa: E402

RUNS = ROOT / "docs/eval/runs"


def means(recall):
    return {"hit_rate": recall, "recall": recall, "precision": 0.1, "mrr": recall / 2, "ndcg": recall / 2}


def runs_with(recalls):
    """One run per name: overall and source:slack rows at k = 5, 10, 20, all with the given recall."""
    runs = Path(tempfile.mkdtemp())
    for name, recall in recalls.items():
        (runs / name).mkdir()
        rows = [{"group": group, "k": k, "questions": 3, "means": means(recall)}
                for group in ("overall", "source:slack") for k in (10, 5, 20)]
        (runs / name / "metrics.json").write_text(json.dumps({"config": {}, "rows": rows}))
    return runs


STEPS = [Step("1. Dense only", "exact", "dense"), Step("2. Sparse only (BM25)", "exact", "sparse")]


class ResultsTables(unittest.TestCase):
    def setUp(self):
        self.markdown = results_tables(STEPS, runs_with({"dense": 0.5, "sparse": 0.75}))

    def test_one_section_per_group_with_k_10_then_5_then_20(self):
        headings = [line for line in self.markdown.splitlines() if line.startswith("#")]
        self.assertEqual(headings, ["### All sources (3 questions)", "#### k = 10", "#### k = 5", "#### k = 20",
                                    "### slack (3 questions)", "#### k = 10", "#### k = 5", "#### k = 20"])

    def test_a_row_per_step_with_the_five_metrics(self):
        self.assertIn("| 1. Dense only | exact | 0.500 | 0.500 | **0.100** | 0.250 | 0.250 |", self.markdown)  # a tie is bold

    def test_the_best_value_of_each_column_is_bold(self):
        self.assertIn("| 2. Sparse only (BM25) | exact | **0.750** | **0.750** | **0.100** | **0.375** | **0.375** |",
                      self.markdown)

    def test_a_step_whose_run_is_missing_names_it(self):
        with self.assertRaisesRegex(FileNotFoundError, "rrf"):
            results_tables([Step("4. Hybrid RRF", "exact", "rrf")], runs_with({}))


class ReplaceGenerated(unittest.TestCase):
    TEXT = "# Results\nhand-written\n<!-- generated: EVAL-5b -->\nold\n<!-- end generated -->\nafter\n"

    def test_only_the_text_between_the_markers_changes(self):
        self.assertEqual(replace_generated(self.TEXT, "new"),
                         "# Results\nhand-written\n<!-- generated: EVAL-5b -->\nnew\n<!-- end generated -->\nafter\n")

    def test_running_twice_gives_the_same_file(self):
        once = replace_generated(self.TEXT, "new")
        self.assertEqual(replace_generated(once, "new"), once)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(tables_module).failed, 0)


@unittest.skipUnless((RUNS / V1_STEPS[-1].run).is_dir(), "needs docs/eval/runs")
class RealRuns(unittest.TestCase):
    def test_v1_is_hybrid_rrf_exact_at_recall_0_722(self):
        markdown = results_tables(V1_STEPS, RUNS)
        overall_k10 = markdown.split("#### k = 10")[1].split("####")[0]
        self.assertIn("| 4. Hybrid RRF (v1) | exact | 0.777 | 0.722 | **0.102** | 0.622 | 0.619 |", overall_k10)


if __name__ == "__main__":
    unittest.main()

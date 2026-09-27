"""EVAL-2b: metrics_report, mean metrics per (group, k): overall, per question type, per source.

One overall number says how good retrieval is; the groups say where it fails. Of the 470
scored questions, confluence has 114, jira 100, slack 79 ... fireflies 25; basic is 175 of
them, completeness 20. 68 questions span 2 to 5 sources and count in each, so the source
rows add up to more than 470. Rows at k = 5, 10, 20 side by side tell a document ranked too
low (recall rises with k) from one not found at all (it does not).

    >>> q = Question("qst_0431", "completeness", ("confluence",), "Emergency rollback?", ("dsid_f6e3", "dsid_8407"))
    >>> for row in metrics_report([Scored(q, 10, {"recall": 0.5, "mrr": 1.0})]):
    ...     print(row)
    ReportRow(group='overall', k=10, questions=1, means={'recall': 0.5, 'mrr': 1.0})
    ReportRow(group='type:completeness', k=10, questions=1, means={'recall': 0.5, 'mrr': 1.0})
    ReportRow(group='source:confluence', k=10, questions=1, means={'recall': 0.5, 'mrr': 1.0})

EVAL-5a: write_run, a run's evidence kept in git: metrics.json (config + these rows) and
scored.jsonl (one line per question and k). Runs used to go to runs/, which is gitignored, and
kept only averages: RET-2 could not say which questions BM25 found that dense missed, and the
eleven runs behind v0 and v1 existed only on this laptop. They now go to docs/eval/runs/<name>/.
"""
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Sequence

from pipeline.eval.questions import Question


class Scored(NamedTuple):
    """One question scored at one k: `metrics` is RetrievalEvalResult.metric_vals_dict."""
    question: Question
    k: int
    metrics: Dict[str, float]


class ReportRow(NamedTuple):
    group: str  # "overall", "type:<question_type>" or "source:<source_type>"
    k: int
    questions: int
    means: Dict[str, float]


def groups_of(question: Question) -> List[str]:
    return ["overall", f"type:{question.question_type}"] + [f"source:{source}" for source in question.source_types]


def metrics_report(scored: Iterable[Scored]) -> List[ReportRow]:
    members = defaultdict(list)
    for one in scored:
        for group in groups_of(one.question):
            members[(group, one.k)].append(one.metrics)
    overall_first = sorted(members, key=lambda group_and_k: group_and_k[0] != "overall")
    return [ReportRow(group, k, len(members[(group, k)]),
                      {name: fmean(metrics[name] for metrics in members[(group, k)]) for name in members[(group, k)][0]})
            for group, k in overall_first]


def write_run(run_dir: Path, config: Mapping[str, Any], scored: Sequence[Scored]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [row._asdict() for row in metrics_report(scored)]
    (run_dir / "metrics.json").write_text(json.dumps({"config": dict(config), "rows": rows}, indent=2) + "\n")
    (run_dir / "scored.jsonl").write_text("".join(
        json.dumps({"question_id": one.question.question_id, "question_type": one.question.question_type,
                    "source_types": list(one.question.source_types), "k": one.k, "metrics": one.metrics}) + "\n"
        for one in scored))

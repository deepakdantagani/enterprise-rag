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
"""
from collections import defaultdict
from statistics import fmean
from typing import Dict, Iterable, List, NamedTuple

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

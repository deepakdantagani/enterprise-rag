"""EVAL-5b: results_tables, the results.md tables generated from the run files, never typed.

Layer 2 of the evaluation report. Every v0 → v1 number used to be copied by hand from
metrics.json into results.md and the stories: 7 steps × 10 groups × 3 k × 5 metrics is 1,050
numbers, too many to copy without a slip. Now one command reads the runs in
docs/eval/runs (EVAL-5a) and rewrites the generated part of docs/eval/results.md: a table per
group (all sources, then each source by question count), at k = 10, 5 and 20, one row per step,
the best value of each metric in bold (every tie, as shown to 3 decimals).

    >>> replace_generated("intro\\n<!-- generated: EVAL-5b -->\\nold\\n<!-- end generated -->\\n", "new")
    'intro\\n<!-- generated: EVAL-5b -->\\nnew\\n<!-- end generated -->\\n'
"""
import json
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "docs/eval/runs"
RESULTS = ROOT / "docs/eval/results.md"
METRICS = ("hit_rate", "recall", "precision", "mrr", "ndcg")
HEADER = "| Step | Search | Hit rate | Recall | Precision | MRR | NDCG |\n|---|---|---|---|---|---|---|"
KS = (10, 5, 20)
START, END = "<!-- generated: EVAL-5b -->", "<!-- end generated -->"


class Step(NamedTuple):
    label: str   # e.g. "4. Hybrid RRF (v1)"
    search: str  # "exact" or "HNSW"
    run: str     # folder name in docs/eval/runs


V1_STEPS = [
    Step("1. Dense only", "exact", "2026-09-27-hybrid__voyage_4__bm25-dense-exact"),
    Step("1. Dense only", "HNSW", "2026-09-27-hybrid__voyage_4__bm25-dense"),
    Step("2. Sparse only (BM25)", "exact", "2026-09-27-hybrid__voyage_4__bm25-sparse"),
    Step("3. Hybrid A (relative)", "exact", "2026-09-27-hybrid__voyage_4__bm25-hybrid-relative-exact"),
    Step("3. Hybrid A (relative)", "HNSW", "2026-09-27-hybrid__voyage_4__bm25-hybrid-relative"),
    Step("4. Hybrid RRF (v1)", "exact", "2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf-exact"),
    Step("4. Hybrid RRF", "HNSW", "2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf"),
]
RERANK_STEPS = [  # RET-6: the reranker chosen for v2; rerank-2.5 and rerank-3 runs stay in docs/eval/runs
    Step("5. v1 + rerank-3-lite (v2)", "exact", "2026-09-27-hybrid__voyage_4__bm25-rrf-rerank-3-lite"),
]
TITLED_STEPS = [  # EVAL-3i: BM25 with titles replaces BM25 without; the untitled runs stay in docs/eval/runs
    Step("1. Dense only", "exact", "2026-09-27-hybrid__voyage_4__bm25-dense-exact"),
    Step("2. BM25 with titles", "exact", "2026-09-27-bm25-titles"),
    Step("3. Hybrid RRF, BM25 with titles", "exact", "2026-09-27-hybrid-rrf-titles-exact"),
    Step("4. Top 100 + rerank-3-lite (v3)", "exact", "2026-09-27-titles-rrf-top100-rerank-3-lite"),
]
REPORT_STEPS = TITLED_STEPS

Rows = Dict[Tuple[str, int], dict]  # (group, k) -> {"questions": n, "means": {...}}


def run_rows(runs_dir: Path, run: str) -> Rows:
    path = runs_dir / run / "metrics.json"
    if not path.is_file():
        raise FileNotFoundError(f"no metrics.json for run {run!r} in {runs_dir}")
    return {(row["group"], row["k"]): row for row in json.loads(path.read_text())["rows"]}


def table(steps: Sequence[Step], rows: List[Rows], group: str, k: int) -> str:
    values = [[round(runs[(group, k)]["means"][metric], 3) for metric in METRICS] for runs in rows]  # compare as shown
    best = [max(column) for column in zip(*values)]
    lines = [f"| {step.label} | {step.search} | " + " | ".join(
        f"**{value:.3f}**" if value == top else f"{value:.3f}" for value, top in zip(row, best)) + " |"
        for step, row in zip(steps, values)]
    return f"#### k = {k}\n\n{HEADER}\n" + "\n".join(lines)


def results_tables(steps: Sequence[Step], runs_dir: Path = RUNS) -> str:
    rows = [run_rows(runs_dir, step.run) for step in steps]
    sources = sorted({group for group, _ in rows[0] if group.startswith("source:")},
                     key=lambda group: -rows[0][(group, 10)]["questions"])
    sections = []
    for group in ["overall"] + sources:
        name = "All sources" if group == "overall" else group.split(":", 1)[1]
        tables = "\n\n".join(table(steps, rows, group, k) for k in KS)
        sections.append(f"### {name} ({rows[0][(group, 10)]['questions']} questions)\n\n{tables}")
    return "\n\n".join(sections)


def replace_generated(text: str, generated: str) -> str:
    return re.sub(f"{re.escape(START)}\n.*?{re.escape(END)}", lambda _: f"{START}\n{generated}\n{END}", text,
                  flags=re.S)


def main() -> None:
    RESULTS.write_text(replace_generated(RESULTS.read_text(), results_tables(REPORT_STEPS)))


if __name__ == "__main__":
    main()

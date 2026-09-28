"""EVAL-5c: html_report, layer 3 of the evaluation report: one self-contained page from the runs.

The v1 step table in results.md shows overall numbers only, yet the runs say more: on the same
470 questions RRF (v1, exact) finds recall@10 0.782 on jira but 0.515 on hubspot. A button per
source (ordered by question count: confluence 114 ... fireflies 25) shows every step for that
source at k = 10, 5 and 20, the best value in each column marked. No number is typed: the page
embeds the rows of each run's metrics.json (EVAL-5a) as JSON and draws the tables from them.

    >>> dense = [{"group": "overall", "k": 10, "questions": 2, "means": {"recall": 0.5}}]
    >>> rrf = [{"group": "overall", "k": 10, "questions": 2, "means": {"recall": 0.7222}}]
    >>> tables_for([dense, rrf], [("dense", "exact"), ("rrf", "exact")], "overall", ("recall",))
    {'10': [{'step': 'dense', 'search': 'exact', 'values': {'recall': 0.5}, 'best': []}, {'step': 'rrf', 'search': 'exact', 'values': {'recall': 0.722}, 'best': ['recall']}]}
"""
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from pipeline.eval.results_tables import REPORT_STEPS, V1_STEPS  # one step list for the tables (EVAL-5b) and this page

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "docs/eval/runs"
REPORT = ROOT / "docs/eval/report.html"
METRICS = ("hit_rate", "recall", "precision", "mrr", "ndcg")
KS = (10, 5, 20)


def load_rows(runs_dir: Path, run_name: str) -> List[dict]:
    metrics = runs_dir / run_name / "metrics.json"
    if not metrics.is_file():
        raise FileNotFoundError(f"run {run_name}: no {metrics}")
    return json.loads(metrics.read_text())["rows"]


def groups_of(rows: List[dict]) -> List[dict]:
    """"All" first, then each source, most questions first."""
    sizes = {row["group"]: row["questions"] for row in rows if row["k"] == 10}
    sources = sorted((group for group in sizes if group.startswith("source:")), key=lambda g: (-sizes[g], g))
    return [{"id": "overall", "name": "All", "questions": sizes["overall"]}] + [
        {"id": group, "name": group.split(":", 1)[1], "questions": sizes[group]} for group in sources]


def tables_for(runs: Sequence[List[dict]], steps: Sequence[Tuple[str, str]], group: str,
               metrics: Sequence[str] = METRICS) -> Dict[str, List[dict]]:
    """One table per k (10, 5, 20): a row per step, values to 3 decimals, the best of each column named."""
    tables = {}
    for k in KS:
        means = [next((row["means"] for row in rows if (row["group"], row["k"]) == (group, k)), None) for rows in runs]
        if None in means:
            continue
        values = [{name: round(one[name], 3) for name in metrics} for one in means]
        tables[str(k)] = [{"step": step, "search": search, "values": value,
                           "best": [name for name in metrics if value[name] == max(v[name] for v in values)]}
                          for (step, search), value in zip(steps, values)]
    return tables


def html_report(steps: Sequence[Tuple[str, str, str]], runs_dir: Path, title: str) -> str:
    runs = [load_rows(runs_dir, run_name) for _, _, run_name in steps]
    groups = groups_of(runs[0])
    step_names = [(label, search) for label, search, _ in steps]
    data = {"groups": groups, "tables": {g["id"]: tables_for(runs, step_names, g["id"]) for g in groups}}
    embedded = json.dumps(data).replace("</", "<\\/")
    return PAGE.replace("{title}", title).replace("{data}", embedded)


def main() -> None:
    REPORT.write_text(html_report(REPORT_STEPS, RUNS, "Retrieval evaluation: v0 → v1 → reranking"))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root { --bg: #fbfbf9; --fg: #1d1d1b; --muted: #6b6b66; --line: #e2e2dc; --accent: #2f6f4f; --best-bg: #e3f1e8; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --fg: #ececea; --muted: #a0a09a; --line: #34342f; --accent: #7cc49c; --best-bg: #1f3a2a; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
       font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 860px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 16px; }
h2 { font-size: 1rem; margin: 24px 0 8px; }
nav { display: flex; flex-wrap: wrap; gap: 8px; }
button { font: inherit; padding: 6px 12px; border: 1px solid var(--line); border-radius: 999px;
         background: transparent; color: var(--fg); cursor: pointer; }
button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.count { color: var(--muted); margin: 16px 0 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th:nth-child(-n+2), td:nth-child(-n+2) { text-align: left; }
th { color: var(--muted); font-weight: 600; }
td.best { background: var(--best-bg); color: var(--accent); font-weight: 700; }
</style></head>
<body><main>
<h1>{title}</h1>
<nav id="groups"></nav>
<p class="count" id="count"></p>
<div id="tables"></div>
</main>
<script id="data" type="application/json">{data}</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const columns = [["hit_rate", "Hit rate"], ["recall", "Recall"], ["precision", "Precision"], ["mrr", "MRR"], ["ndcg", "NDCG"]];
const cell = (tag, text, cls) => { const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el; };
function show(group) {
  document.querySelectorAll("#groups button").forEach(b => b.setAttribute("aria-pressed", b.dataset.id === group.id));
  document.getElementById("count").textContent = group.questions + " questions";
  const out = document.getElementById("tables"); out.replaceChildren();
  for (const [k, rows] of Object.entries(data.tables[group.id]).sort((a, b) => [10, 5, 20].indexOf(+a[0]) - [10, 5, 20].indexOf(+b[0]))) {
    out.append(cell("h2", "k = " + k));
    const table = document.createElement("table"), head = table.insertRow();
    ["Step", "Search"].concat(columns.map(c => c[1])).forEach(h => head.append(cell("th", h)));
    for (const row of rows) {
      const tr = table.insertRow(); tr.append(cell("td", row.step), cell("td", row.search));
      columns.forEach(([m]) => tr.append(cell("td", row.values[m].toFixed(3), row.best.includes(m) ? "best" : "")));
    }
    const wrap = cell("div", "", "scroll"); wrap.append(table); out.append(wrap);
  }
}
for (const group of data.groups) {
  const b = cell("button", group.name); b.dataset.id = group.id; b.onclick = () => show(group);
  document.getElementById("groups").append(b);
}
show(data.groups[0]);
</script>
</body></html>
"""

if __name__ == "__main__":
    main()

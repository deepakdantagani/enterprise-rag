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
TITLE = "EnterpriseRAG Retrieval Scoreboard"
VERSIONS = (  # each version is one change on the one before, scored exactly on the 470 questions
    ("v0", "2026-09-27-hybrid__voyage_4__bm25-dense-exact", "Dense search: voyage-4 vectors"),
    ("v1", "2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf-exact", "+ BM25, fused by RRF"),
    ("v2", "2026-09-27-hybrid__voyage_4__bm25-rrf-rerank-3-lite", "+ rerank-3-lite on the top 50"),
)


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


def version_summary(runs_dir: Path, versions: Sequence[Tuple[str, str, str]]) -> List[dict]:
    """Each version's overall recall@10 and MRR@10, and its recall gain over the version before."""
    summary, previous = [], None
    for name, run_name, about in versions:
        at_10 = next(row["means"] for row in load_rows(runs_dir, run_name) if (row["group"], row["k"]) == ("overall", 10))
        recall = round(at_10["recall"], 3)
        summary.append({"name": name, "about": about, "recall": recall, "mrr": round(at_10["mrr"], 3),
                        "gain": None if previous is None else round(recall - previous, 3)})
        previous = recall
    return summary


def html_report(steps: Sequence[Tuple[str, str, str]], runs_dir: Path, title: str,
                versions: Sequence[Tuple[str, str, str]] = ()) -> str:
    runs = [load_rows(runs_dir, run_name) for _, _, run_name in steps]
    groups = groups_of(runs[0])
    step_names = [(label, search) for label, search, _ in steps]
    data = {"groups": groups, "tables": {g["id"]: tables_for(runs, step_names, g["id"]) for g in groups},
            "versions": version_summary(runs_dir, versions)}
    embedded = json.dumps(data).replace("</", "<\\/")
    return PAGE.replace("{title}", title).replace("{data}", embedded)


def main() -> None:
    REPORT.write_text(html_report(REPORT_STEPS, RUNS, TITLE, versions=VERSIONS))


PAGE = """<meta charset="utf-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {
  --ground: #f5f7f5; --surface: #ffffff; --ink: #17211e; --muted: #5c6a65; --line: #dce3df;
  --accent: #17705a; --accent-soft: #ddefe8; --gain: #17705a;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground: #111715; --surface: #18201d; --ink: #e4ebe8; --muted: #93a29c; --line: #2a3632;
    --accent: #67c6a6; --accent-soft: #173a2f; --gain: #67c6a6;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground: #111715; --surface: #18201d; --ink: #e4ebe8; --muted: #93a29c; --line: #2a3632;
  --accent: #67c6a6; --accent-soft: #173a2f; --gain: #67c6a6;
}
body { background: var(--ground); color: var(--ink); font: 15px/1.55 var(--sans); padding: 28px 16px 40px; }
main { max-width: 900px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; }
section { min-width: 0; display: grid; gap: 10px; }
h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: -0.01em; margin: 0; text-wrap: balance; }
.lede { color: var(--muted); margin: 6px 0 0; max-width: 65ch; }
.label { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.versions { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.version { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
           display: grid; gap: 4px; }
.version.current { border-color: var(--accent); }
.version .figure { font: 500 2rem/1.1 var(--mono); font-variant-numeric: tabular-nums; }
.version .figure small { font-size: 0.8rem; color: var(--muted); font-weight: 400; }
.version .about { color: var(--muted); font-size: 0.9rem; }
.version .gain { font: 0.85rem var(--mono); color: var(--gain); }
.bar { height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--accent); }
nav { display: flex; flex-wrap: wrap; gap: 8px; }
button { font: 500 0.9rem var(--sans); padding: 6px 12px; border: 1px solid var(--line); border-radius: 6px;
         background: var(--surface); color: var(--ink); cursor: pointer; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--ground); }
.count { color: var(--muted); margin: 0; }
h2 { font-size: 1rem; font-weight: 600; margin: 18px 0 8px; }
.scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font: 0.88rem var(--mono); font-variant-numeric: tabular-nums; }
th, td { padding: 7px 12px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
th:nth-child(-n+2), td:nth-child(-n+2) { text-align: left; font-family: var(--sans); }
th { color: var(--muted); font: 500 0.72rem var(--sans); letter-spacing: 0.06em; text-transform: uppercase; }
tr.current td:first-child { color: var(--accent); font-weight: 600; }
td.best { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
footer { color: var(--muted); font-size: 0.85rem; max-width: 65ch; }
code { font-family: var(--mono); font-size: 0.85em; }
</style>
<main>
  <header>
    <div class="label">EnterpriseRAG-Bench · 470 questions · exact search</div>
    <h1>{title}</h1>
    <p class="lede">Document recall and ranking for every retrieval step, overall and per source. Each version adds one change to the one before; highlighted cells are the best in their column.</p>
  </header>
  <section aria-labelledby="versions-title">
    <div class="label" id="versions-title">Recall@10 by version</div>
    <div class="versions" id="versions"></div>
  </section>
  <section aria-labelledby="steps-title">
    <div class="label" id="steps-title">Every step, by source</div>
    <nav id="groups" aria-label="Source"></nav>
    <p class="count" id="count"></p>
    <div id="tables"></div>
  </section>
  <footer>Generated from the run files in <code>docs/eval/runs</code> by <code>python -m pipeline.eval.html_report</code>. "HNSW" rows use Qdrant's approximate graph index; every other row searches every vector. A question counts under each source of its expected documents.</footer>
</main>
<script id="data" type="application/json">{data}</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const columns = [["hit_rate", "Hit rate"], ["recall", "Recall"], ["precision", "Precision"], ["mrr", "MRR"], ["ndcg", "NDCG"]];
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
const current = data.versions.length ? data.versions[data.versions.length - 1] : null;
data.versions.forEach(v => {
  const card = el("div", undefined, "version" + (v === current ? " current" : ""));
  const figure = el("div", v.recall.toFixed(3), "figure"); figure.append(el("small", "  MRR " + v.mrr.toFixed(3)));
  const bar = el("div", undefined, "bar"); const fill = el("span"); fill.style.width = (v.recall * 100) + "%"; bar.append(fill);
  card.append(el("div", v.name + (v === current ? " · current" : ""), "label"), figure, bar, el("div", v.about, "about"),
              el("div", v.gain === null ? "baseline" : "+" + v.gain.toFixed(3) + " over " + data.versions[data.versions.indexOf(v) - 1].name, "gain"));
  document.getElementById("versions").append(card);
});
function show(group) {
  document.querySelectorAll("#groups button").forEach(b => b.setAttribute("aria-pressed", b.dataset.id === group.id));
  document.getElementById("count").textContent = (group.id === "overall" ? "All sources" : group.name) + " · " + group.questions + " questions";
  const out = document.getElementById("tables"); out.replaceChildren();
  for (const k of ["10", "5", "20"]) {
    const rows = data.tables[group.id][k]; if (!rows) continue;
    out.append(el("h2", "k = " + k));
    const table = document.createElement("table"), head = table.insertRow();
    ["Step", "Search"].concat(columns.map(c => c[1])).forEach(h => head.append(el("th", h)));
    for (const row of rows) {
      const tr = table.insertRow(); if (row.step.includes("(v2)")) tr.className = "current";
      tr.append(el("td", row.step), el("td", row.search));
      columns.forEach(([m]) => tr.append(el("td", row.values[m].toFixed(3), row.best.includes(m) ? "best" : "")));
    }
    const wrap = el("div", undefined, "scroll"); wrap.append(table); out.append(wrap);
  }
}
for (const group of data.groups) {
  const b = el("button", group.name); b.dataset.id = group.id; b.onclick = () => show(group);
  document.getElementById("groups").append(b);
}
show(data.groups[0]);
</script>
"""

if __name__ == "__main__":
    main()

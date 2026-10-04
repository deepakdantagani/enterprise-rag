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
ANSWERS = ("2026-10-04-answers-v4-gemma4-v2",  # GEN-11b: the base answer run (retrieval v4, ANSWER_PROMPT_V2)
           "2026-10-04-answers-v4-deepseek-v4-pro-v2")  # GEN-12b: the same documents and prompt on deepseek-v4-pro
VERSIONS = (  # each version is one change on the one before, scored exactly on the 470 questions
    ("v0", "2026-09-27-hybrid__voyage_4__bm25-dense-exact", "Dense search: voyage-4 vectors"),
    ("v1", "2026-09-27-hybrid__voyage_4__bm25-hybrid-rrf-exact", "+ BM25, fused by RRF"),
    ("v2", "2026-09-27-hybrid__voyage_4__bm25-rrf-rerank-3-lite", "+ rerank-3-lite on the top 50"),
    ("v3", "2026-09-27-titles-rrf-top100-rerank-3-lite", "+ titles in BM25, the top 100 reranked"),
    ("v4", "2026-09-28-titles__voyage_4_lite__bm25-rrf-top100-rerank-3-lite",
     "dense on voyage-4-lite: a third of the cost, within noise"),
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


def answer_summary(runs_dir: Path, run_name: str, retrieval: List[dict]) -> dict:
    """GEN-11b: the judged answers per source, largest first, with the last retrieval step's recall@10 beside."""
    saved = json.loads((runs_dir / run_name / "metrics.json").read_text())
    recall = {row["group"]: round(row["means"]["recall"], 3) for row in retrieval if row["k"] == 10}
    rows = sorted(saved["rows"], key=lambda row: (row["group"] != "overall", -row["questions"], row["group"]))
    names = {"overall": "All", "source:none": "no expected document"}
    return {"config": saved["config"], "rows": [
        {"name": names.get(row["group"], row["group"].split(":", 1)[-1]), "questions": row["questions"],
         "recall": recall.get(row["group"]), **{name: round(value, 3) for name, value in row["means"].items()}}
        for row in rows]}


def answer_runs(runs_dir: Path, run_names: Sequence[str], retrieval: List[dict]) -> List[dict]:
    """GEN-12b: each answer run's rows, its overall score, and its gain over the run before."""
    runs, previous = [], None
    for run_name in run_names:
        summary = answer_summary(runs_dir, run_name, retrieval)
        score = summary["rows"][0]["score"]
        runs.append({**summary, "score": score, "gain": None if previous is None else round(score - previous, 3)})
        previous = score
    return runs


def html_report(steps: Sequence[Tuple[str, str, str]], runs_dir: Path, title: str,
                versions: Sequence[Tuple[str, str, str]] = (), answers: Sequence[str] = ()) -> str:
    runs = [load_rows(runs_dir, run_name) for _, _, run_name in steps]
    groups = groups_of(runs[0])
    step_names = [(label, search) for label, search, _ in steps]
    data = {"groups": groups, "tables": {g["id"]: tables_for(runs, step_names, g["id"]) for g in groups},
            "versions": version_summary(runs_dir, versions),
            "answers": answer_runs(runs_dir, answers, runs[-1])}
    embedded = json.dumps(data).replace("</", "<\\/")
    return PAGE.replace("{title}", title).replace("{data}", embedded)


def main() -> None:
    REPORT.write_text(html_report(REPORT_STEPS, RUNS, TITLE, versions=VERSIONS, answers=ANSWERS))


PAGE = """<meta charset="utf-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {
  --ground: #f5f7f5; --surface: #ffffff; --ink: #17211e; --muted: #5c6a65; --line: #dce3df;
  --accent: #17705a; --accent-soft: #ddefe8; --gain: #17705a; --weak: #9a4a12; --weak-soft: #f6e6d8;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground: #111715; --surface: #18201d; --ink: #e4ebe8; --muted: #93a29c; --line: #2a3632;
    --accent: #67c6a6; --accent-soft: #173a2f; --gain: #67c6a6; --weak: #e8a56c; --weak-soft: #3d2a1a;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground: #111715; --surface: #18201d; --ink: #e4ebe8; --muted: #93a29c; --line: #2a3632;
  --accent: #67c6a6; --accent-soft: #173a2f; --gain: #67c6a6; --weak: #e8a56c; --weak-soft: #3d2a1a;
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
td.weak { background: var(--weak-soft); color: var(--weak); font-weight: 500; }
#answers-table th:nth-child(2), #answers-table td:nth-child(2) { text-align: right; font-family: var(--mono); }
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
  <section aria-labelledby="answers-title" id="answers" hidden>
    <div class="label" id="answers-title">Answer score by answering model</div>
    <div class="versions" id="answer-cards"></div>
    <div class="label">Answers by source</div>
    <nav id="answer-runs" aria-label="Answering model"></nav>
    <p class="count" id="answers-about"></p>
    <div class="scroll"><table id="answers-table"></table></div>
    <p class="count">Recall@10 is the retrieval step the answerer reads from, on the 470 questions that have expected documents. Correct and complete are judged per answer; score is correct × completeness, the leaderboard's number, so a wrong answer scores 0 however complete it is. Shaded cells are the weakest source in each column.</p>
  </section>
  <footer>Generated from the run files in <code>docs/eval/runs</code> by <code>python -m pipeline.eval.html_report</code>. "HNSW" rows use Qdrant's approximate graph index; every other row searches every vector. Answer rows come from <code>python -m pipeline.eval.answer_metrics</code>. A question counts under each source of its expected documents.</footer>
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
              el("div", v.gain === null ? "baseline" : (v.gain < 0 ? "\u2212" + (-v.gain).toFixed(3) : "+" + v.gain.toFixed(3)) + " over " + data.versions[data.versions.indexOf(v) - 1].name, "gain"));
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
      const tr = table.insertRow(); if (current && row.step.includes("(" + current.name + ")")) tr.className = "current";
      tr.append(el("td", row.step), el("td", row.search));
      columns.forEach(([m]) => tr.append(el("td", row.values[m].toFixed(3), row.best.includes(m) ? "best" : "")));
    }
    const wrap = el("div", undefined, "scroll"); wrap.append(table); out.append(wrap);
  }
}
const shown = [["recall", "Recall@10", v => v.toFixed(3)], ["correct", "Correct", v => (v * 100).toFixed(1) + "%"],
               ["completeness", "Complete", v => (v * 100).toFixed(1) + "%"], ["score", "Score", v => (v * 100).toFixed(1)]];
function showAnswers(run) {
  const c = run.config, rows = run.rows, table = document.getElementById("answers-table"); table.replaceChildren();
  document.querySelectorAll("#answer-runs button").forEach(b => b.setAttribute("aria-pressed", b.dataset.id === c.answerer));
  document.getElementById("answers-about").textContent = rows[0].questions + " questions · " + c.prompt + " · answered by " + c.answerer + " · judged by " + c.judge + " (our judge, not the leaderboard's)";
  const head = table.insertRow(); ["Source", "Questions"].concat(shown.map(s => s[1])).forEach(h => head.append(el("th", h)));
  const weakest = Object.fromEntries(shown.map(([m]) => [m, Math.min(...rows.slice(1).map(r => r[m]).filter(v => v !== null))]));
  rows.forEach((row, i) => {
    const tr = table.insertRow(); if (i === 0) tr.className = "current";
    tr.append(el("td", row.name), el("td", String(row.questions)));
    shown.forEach(([m, , format]) => tr.append(el("td", row[m] === null ? "n/a" : format(row[m]), i > 0 && row[m] === weakest[m] ? "weak" : "")));
  });
}
if (data.answers.length) {
  const latest = data.answers[data.answers.length - 1];
  document.getElementById("answers").hidden = false;
  data.answers.forEach((run, i) => {
    const card = el("div", undefined, "version" + (run === latest ? " current" : ""));
    const figure = el("div", (run.score * 100).toFixed(1), "figure"); figure.append(el("small", "  " + (run.rows[0].correct * 100).toFixed(1) + "% correct"));
    const bar = el("div", undefined, "bar"); const fill = el("span"); fill.style.width = (run.score * 100) + "%"; bar.append(fill);
    card.append(el("div", run.config.answerer + (run === latest ? " · current" : ""), "label"), figure, bar,
                el("div", i === 0 ? "Base: 10 whole documents from v4, prompt v2" : "Same documents and prompt, a stronger model", "about"),
                el("div", run.gain === null ? "baseline" : (run.gain < 0 ? "\u2212" + (-run.gain * 100).toFixed(1) : "+" + (run.gain * 100).toFixed(1)) + " over " + data.answers[i - 1].config.answerer, "gain"));
    document.getElementById("answer-cards").append(card);
    const b = el("button", run.config.answerer); b.dataset.id = run.config.answerer; b.onclick = () => showAnswers(run);
    document.getElementById("answer-runs").append(b);
  });
  showAnswers(latest);
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

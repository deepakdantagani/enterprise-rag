"""Run the llamaindex-docs skill against its ground truth and grade the answers.

Each case runs as a fresh headless session (`claude -p`) from the repo root, so the
skill has to trigger from its description alone, the way it would for Deepak.
Grading is deterministic: did the skill fire as expected (read from the stream-json
tool calls), and does the final answer contain the expected terms.

    uv run python .claude/skills/llamaindex-docs/evals/run_evals.py            # all cases
    uv run python .claude/skills/llamaindex-docs/evals/run_evals.py node-parsers chat-engines
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[3]
SKILL = "llamaindex-docs"
ALLOWED = "Skill Read Grep Glob Bash(curl:*) Bash(grep:*) Bash(python3:*) WebFetch"


def run_case(case):
    """One headless session -> (skill_fired, answer_text)."""
    out = subprocess.run(
        ["claude", "-p", case["question"], "--output-format", "stream-json",
         "--verbose", "--allowedTools", ALLOWED],
        cwd=ROOT, capture_output=True, text=True, timeout=600,
    ).stdout
    fired, answer = False, ""
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Skill" \
                        and block.get("input", {}).get("skill") == SKILL:
                    fired = True
        if event.get("type") == "result":
            answer = event.get("result", "")
    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "runs" / f"{case['id']}.txt").write_text(answer)
    return fired, answer


def grade(case, fired, answer):
    """-> list of failure reasons; empty means pass."""
    text = answer.lower()
    failures = []
    if fired != case["expect_skill"]:
        failures.append(f"skill fired={fired}, expected {case['expect_skill']}")
    missing = [t for t in case.get("must_include", []) if t.lower() not in text]
    if missing:
        failures.append(f"missing {missing}")
    for group in case.get("must_include_any", []):
        if not any(t.lower() in text for t in group):
            failures.append(f"none of {group}")
    return failures


def main(ids):
    cases = json.loads((HERE / "ground_truth.json").read_text())["cases"]
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run_case, cases))
    passed = 0
    for case, (fired, answer) in zip(cases, results):
        failures = grade(case, fired, answer)
        passed += not failures
        print(f"{'PASS' if not failures else 'FAIL'}  {case['id']:<22} {'; '.join(failures)}")
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

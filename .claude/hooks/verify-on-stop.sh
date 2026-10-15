#!/bin/bash
# Stop hook: if the turn changed Python, run the fast checks — doctests of changed modules and the
# test files that changed. Tests that import a changed module can read the whole corpus (~4 min for
# the Slack ones), so they and the full suite run in /open-pr, not on every turn.
input=$(cat)
[ "$(echo "$input" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
changed=$(git status --porcelain -- '*.py' | awk '{print $NF}' | grep -Ev '^archive/|__init__\.py$')
[ -z "$changed" ] && exit 0
modules=$(echo "$changed" | grep -E '^(pipeline|tools)/' | sed 's#\.py$##; s#/#.#g' | tr '\n' ' ')
tests=$(echo "$changed" | grep -E '^tests/test_.*\.py$' | sed 's#\.py$##; s#/#.#g' | tr '\n' ' ')
out=""; failed=0
if [ -n "${modules// }" ]; then
  out=$(uv run python -c '
import doctest, importlib, sys
bad = [m for m in sys.argv[1:] if doctest.testmod(importlib.import_module(m)).failed]
sys.exit("doctests failing in: " + " ".join(bad) if bad else 0)' $modules 2>&1) || failed=1
fi
if [ -n "${tests// }" ]; then
  out="$out$(uv run python -m unittest $tests 2>&1)" || failed=1
fi
if [ $failed -ne 0 ]; then
  echo "Checks are failing. Fix the root cause (don't weaken tests or edit a golden to make it pass):" >&2
  echo "$out" | tail -40 >&2
  exit 2
fi
exit 0

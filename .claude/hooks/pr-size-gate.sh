#!/bin/bash
# Blocks `gh pr create` when the branch's Python change is too big for one story PR.
# Counts *.py lines only (code + tests); story docs and goldens don't count. Target is ~60 lines;
# the gate sits higher so a story with a long doctest or fixture still passes.
cmd=$(jq -r '.tool_input.command // empty')
echo "$cmd" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+create' || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
MAX_LINES=${PR_MAX_LINES:-200}; MAX_FILES=${PR_MAX_FILES:-6}
base=origin/master; git rev-parse -q --verify "$base" >/dev/null || base=master
stats=$(git diff --numstat "$base"...HEAD -- '*.py' ':(exclude)archive/**')
lines=$(echo "$stats" | awk '$1!="-"{s+=$1+$2} END{print s+0}')
files=$(echo "$stats" | grep -c .)
if [ "$lines" -gt "$MAX_LINES" ] || [ "$files" -gt "$MAX_FILES" ]; then
  echo "PR too big: $lines Python lines in $files files (limit $MAX_LINES / $MAX_FILES). One story = one function: split into sub-stories (a, b, c)." >&2
  exit 2
fi
exit 0

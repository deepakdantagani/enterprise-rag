#!/bin/bash
# Blocks shell commands that leak keys, destroy the corpus, or write to master.
input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // empty')
dir=$(echo "$input" | jq -r '.cwd // empty'); dir=${dir:-${CLAUDE_PROJECT_DIR:-.}}
block() { echo "$1" >&2; exit 2; }

echo "$cmd" | grep -Eq '(cat|less|head|tail|more|grep|source|\.)[[:space:]]+[^|;]*\.env([[:space:]]|$|\.local)' \
  && block "Reading .env from the shell is blocked."
# data/ is gitignored and, in a worktree, a symlink to the main checkout: deleting it loses the corpus everywhere.
echo "$cmd" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rRf][^|;&]*[[:space:]](\./)?data/?([[:space:]]|$)' \
  && block "Deleting data/ is blocked: it is shared by every worktree and is not in git. Delete only the generated folder you mean."
echo "$cmd" | grep -Eq 'git[[:space:]]+push[^|;&]*(--force|-f)([[:space:]]|$)' && echo "$cmd" | grep -q master \
  && block "Force-pushing to master is blocked."
echo "$cmd" | grep -Eq 'git[[:space:]]+push[^|;&]*([[:space:]]|:)(master|HEAD:master|refs/heads/master)([[:space:]]|$)' \
  && block "Pushing to master is blocked. Push the story branch and open a PR."
if echo "$cmd" | grep -Eq 'git[[:space:]]+(commit|merge|rebase|cherry-pick)([[:space:]]|$)' \
   && [ "$(git -C "$dir" branch --show-current 2>/dev/null)" = "master" ]; then
  block "Changing master locally is blocked. Work on a story branch (git switch -c claude/<story-id>-...)."
fi
exit 0

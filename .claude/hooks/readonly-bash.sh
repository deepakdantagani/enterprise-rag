#!/bin/bash
# For read-only agents (reviewer, auditor, analyst, architect): allow inspection, block anything that writes or spends money.
cmd=$(jq -r '.tool_input.command // empty')
if echo "$cmd" | grep -Eq '(^|[;&|[:space:]])(rm|mv|cp|tee|touch|mkdir|chmod|truncate|dd)[[:space:]]|sed[[:space:]]+-i|>[[:space:]]*[^&]|git[[:space:]]+(commit|push|reset|checkout|switch|merge|rebase|apply|stash|add)|uv[[:space:]]+(add|remove|sync)|pip[[:space:]]+install|gh[[:space:]]+pr[[:space:]]+(create|merge|close)'; then
  echo "This agent is read-only: commands that modify files, git, or packages are blocked. Report the change instead." >&2; exit 2
fi
# Eval runs call Voyage / DeepSeek / OpenAI; only the main session runs them, after a cost estimate.
if echo "$cmd" | grep -Eq 'python[^|;&]*-m[[:space:]]+pipeline\.eval\.'; then
  echo "Running pipeline.eval modules can call paid APIs. Report the command and its cost estimate instead." >&2; exit 2
fi
exit 0

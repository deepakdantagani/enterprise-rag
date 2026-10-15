---
name: open-pr
description: Finish a story branch and open its PR — full suite green, goldens unchanged, review by fresh subagents, story marked done. Use when a story's code is done and it is time for the PR.
argument-hint: "<story id>"
---

Open the PR for story $ARGUMENTS.

1. Run the full suite: `uv run python -m unittest discover tests` (about 7 min with `data/`). Show the last lines. Any failure: fix the root cause, never weaken a test.
2. `git diff master...HEAD --stat`: only files the story needs. Python change about 60 lines; the PR gate blocks above 200.
3. Run the `code-reviewer` and `comprehension-reviewer` subagents on the diff in parallel. Fix correctness findings; list the optional ones in the PR.
4. Mark the story ✅ in its stage file and in the index in `docs/stories.md`.
5. Commit, push the branch, `gh pr create` with: story link, what changed, real before/after, test evidence, audit counts.

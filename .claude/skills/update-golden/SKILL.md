---
name: update-golden
description: Deliberately change a golden fingerprint or truth set when a story changes corpus output on purpose. Use only when a story's acceptance criteria say the clean/markdown output changes; never to make a failing test pass.
argument-hint: "<story id>"
disable-model-invocation: true
---

Update goldens for story $ARGUMENTS.

1. Quote the line of the story that says the output changes. If there is none, stop: a failing golden means the change broke behaviour.
2. Regenerate the corpus output on master and on this branch, then diff per file (the manifest sha256 per row shows exactly which files changed). Report: files changed, and 3 real before/after examples.
3. Every changed file must be explained by the story. Any unexplained file is a bug; stop and report it.
4. Truth sets (`tests/fixtures/*/expected.json`): precision must not drop. Show before/after precision.
5. Update `tests/golden/<name>_fingerprint.json` (a permission prompt will ask; that is expected).
6. Commit with the new count in the message, e.g. `SLACK-12: pins 1,204 messages`.

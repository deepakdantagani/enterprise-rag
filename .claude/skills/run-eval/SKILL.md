---
name: run-eval
description: Run a paid eval or answer run safely — cost estimate first, explicit yes, resume-safe run, then analysis. Use whenever a pipeline.eval module that calls Voyage, DeepSeek, OpenAI or another paid API is about to run.
argument-hint: "<module and arguments>"
---

Run eval: $ARGUMENTS

1. Read the module's docstring for what it calls and how it resumes (`pipeline/eval/resume.py`).
2. Estimate cost: number of calls (questions x models x retries), tokens per call, price per million tokens from the provider's current pricing page. Show it as a small table with the total in US$.
3. Ask Deepak for a yes with that number. No yes, no run.
4. Run it in the background with its run log, so a crash can resume instead of paying twice.
5. When it finishes, run the `eval-analyst` subagent to compare against the current base and report before/after numbers and the flipped questions.

---
name: groom-story
description: Write or split a story so a new teammate can read it cold — template from docs/stories.md, real before/after from the corpus, measured counts, index row. Use when asked to write, groom, add or split a story (PARSE-n, SLACK-n, GMAIL-n, LINEAR-n, RET-n, GEN-n, or a new DEPLOY-n).
argument-hint: "<story id or idea>"
---

Groom story: $ARGUMENTS

1. Read `docs/stories.md` (rules, template, glossary, index) and the stage file in `docs/stories/` the story belongs to. A new stage gets the next free number in the index.
2. Run the `corpus-auditor` subagent for the pattern the story targets, so every edge case and count comes from the whole corpus before any test is designed. Skip for stories that don't touch the corpus (deploy, tooling) and say so.
3. Write the story in template order: Status · As a · I want to · So that · Acceptance Criteria (Gherkin, one scenario per edge case) · Example with real data (actual file name and lines, before -> after) · Non-functional Requirements · Dependencies.
4. Size: one function, about 60 lines with tests. If bigger, split into a, b, c sub-stories that each merge alone.
5. Self-contained: define every term in the file's glossary or inline; no "as discussed". Put the why in the story, not in chat.
6. Add or update the index row in `docs/stories.md` (⬜ To do).
7. Show the story to Deepak and stop. Don't start the code; that is `/story`.

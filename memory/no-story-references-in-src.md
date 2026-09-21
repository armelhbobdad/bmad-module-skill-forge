---
created: "2026-05-26 18:47"
session: "38fc2086-0747-4109-a450-5cefe58ae53c"
source: claude-mem
source_table: observations
source_ids: [13509, 13529]
---

# No internal story references in shipped src/ files

Files shipped under `src/` — SKILL.md workflow docs, `references/*.md`, and Python script docstrings — must not carry internal story-tracking references such as "Story 2.7" or "(implemented by story 2.7)". Two story-automator review passes had to strip them: `src/shared/scripts/skf-validate-pins.py`, whose docstring read "Story 2.7 deepwiki --pin) and campaign workflows (Story 4.4)", and the deepwiki pipeline note in `src/skf-forger/SKILL.md`. Stories live under the gitignored `_bmad-output/`, so such a reference points public readers and the npm package at nothing; `CONTRIBUTING.md` records the same rule only for PR bodies ("do not reference internal IDs under `_bmad-output/todo/`"), not for source content, and no linter checks it. Story numbers in `test/` docstrings and `.github/workflows/` comments were left alone — the rule is about what ships (`.npmignore` excludes `test/` and `.github`).

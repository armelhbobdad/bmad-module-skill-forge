---
created: "2026-04-27 09:36"
session: "4413807b-d437-4757-bb96-ea6cb8c785dd"
source: claude-mem
source_table: observations
source_ids: [7633, 7640, 7643, 7650]
---

# bmad-builder script fixes belong in the fork, not the installed .claude copy

`.gitignore` ignores the whole `.claude/` directory, so `.claude/skills/bmad-workflow-builder/scripts/*.py` (for example `prepass-workflow-integrity.py`) is an installed copy of the bmad-builder skill: an edit there is local-only, disappears on the next reinstall and never reaches a PR. The user caught a workflow-integrity scanner fix that had landed only in that installed copy while the upstream PR carried test files alone: "You applied the fix in the installed bmad-builder artefact but I am not seeing that changes in the upstream PR too. I just see the test files." Fixes to bmad-builder tooling go in a local checkout of the bmad-builder fork (origin `armelhbobdad/bmad-builder`, upstream `bmad-code-org/bmad-builder`) under `skills/bmad-workflow-builder/scripts/`, on a branch pushed to origin and opened as a PR against `bmad-code-org/bmad-builder` (the prepass fix lives on branch `fix/prepass-walks-steps-c-and-recognizes-step-naming`, commit ccfb2b0). The installed copy is reset on every reinstall, which is why it is never the place to keep a change.

---
created: "2026-10-03 18:46"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Brief Skill's module pick and its [auto] route are deliberate (accepted exceptions)

Two BMad Builder findings on skf-brief-skill in step 5b gate run 3 (2026-10-03-1402-run3) were verified real and accepted by the maintainer on 2026-10-03 as written exceptions, so later quality runs list them under `excluded_findings` with this note as their reason.

- **The module pick is the model's judgment (determinism-1).** `skf-detect-workspaces.py` lists module candidates and names no modules: its docstring says which folders are the modules is the caller's judgment, `test/test-skf-detect-workspaces.py` asserts the snapshot carries no `module_count`, `module_dirs` or `module_basis`, and commit 96a71c22 records why. The analysis step picks the modules, and the brief payload carries that pick as `module_count`, the one count the payload holds (`references/scope-definition.md` says so).
- **[auto] is its own route (enhancement-1).** An `[auto]` brief and a headless `from_brief` ratify both write an analyze-source brief, through separate steps. `[auto]` is a documented public contract (`docs/forge-auto.md`): the forge-auto pipeline gives it doc enrichment (`step-auto-brief.md` sections 2 and 3), which the ratify and derive routes do not run, and an envelope with `mode: "auto"`, so it stays a separate route by design, as `SKILL.md`'s Stages paragraph says. Shared work such as QMD registration runs through the same section on both routes rather than a copy.

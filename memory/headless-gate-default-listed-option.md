---
created: "2026-04-09 00:25"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: observations
source_ids: [4914]
---

# Every GATE needs a headless default that is a listed option

Headless pipelines hung when skf-drop-skill's and skf-rename-skill's final Y/N confirmation gates carried no `GATE [default: …]` annotation, and skf-verify-stack's report menu declared `GATE [default: C]` although that menu only offers `[R] Review` / `[X] Exit` — an unlisted default is a choice the agent cannot execute, so it waits forever. The fix (2026-04-08) added `GATE [default: Y]` with auto-confirm logging to `src/skf-drop-skill/references/select.md` and `src/skf-rename-skill/references/select.md`, and changed verify-stack's `references/report.md` to `GATE [default: X]`. Nothing in `test/` or `tools/validate-skills.js` checks this and `src/shared/references/headless-gate-convention.md` only says the default is "documented in step file": when adding or editing any menu, verify by hand that its `GATE [default: X]` names an option actually listed in that menu and carries the convention's `headless: auto-…` log line.

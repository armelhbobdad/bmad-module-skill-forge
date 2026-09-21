---
created: "2026-04-09 00:26"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: observations
source_ids: [4918, 4945]
---

# SKILL.md Stages table drifting from step-file GATE annotations

Gate metadata for every workflow skill lives in three places — the `**GATE [default: X]**` annotation in the step file (28 step files; pattern defined in `src/shared/references/headless-gate-convention.md`), the `Auto-proceed` column of the SKILL.md Stages table (14 skills), and the `Gates` row of the Invocation Contract — and only the step-file annotation is the source of truth. In April 2026 skf-analyze-source's table had steps 1-3 inverted and skf-verify-stack marked step 6 `Yes` despite `GATE [default: X]` in the step; the same drift is live at v2.1.0: `src/skf-analyze-source/references/map-and-detect.md:195` reads `**GATE [default: C]** — present the menu and wait for the user's choice` while `src/skf-analyze-source/SKILL.md:41` lists step 4 as `Yes` and the Gates row (`SKILL.md:58`) names only steps 2/3/5. No test or validator cross-checks the three (test-skf-chain-reachability.py only checks paths), so after touching any gate re-derive the Stages table and Gates row from the step files by hand. A wrong `Yes` makes an interactive run skip a confirmation or a headless run stall on a menu the table said would auto-proceed.

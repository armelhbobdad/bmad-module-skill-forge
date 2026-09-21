---
created: "2026-05-21 10:41"
session: "c28d21cc-4bc1-470b-80ac-f37b8f270bd6"
source: claude-mem
source_table: both
source_ids: [10439, 10441, 10455]
---

# continue.md resume route table drift versus nextStepFile chain

`skf-analyze-source` routes twice: forward through each step's `nextStepFile`, and on resume through `references/continue.md` — its `nextStepOptions` frontmatter, the §4 "Last Completed → Next Step" table and the terminal condition. `test/test-skf-chain-reachability.py` validates only the forward chain, so when health-check became step 7 the continue.md table still stopped at `recommend → generate-briefs` and the terminal branch read "IF all steps completed": a resumed session could declare the analysis complete and skip health-check while every test passed (fixed in PR #351, commit 402e0ca3). When adding or renaming a step in `src/skf-analyze-source/SKILL.md`'s Stages table, also add it to continue.md's `nextStepOptions`, add the table row, and keep the terminal check on the specific last step (`IF health-check is in stepsCompleted`), never a generic "done". continue.md is the only resume router under src/ today; any skill that gains one inherits the same untested surface.

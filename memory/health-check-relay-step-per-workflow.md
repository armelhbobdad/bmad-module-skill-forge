---
created: "2026-04-12 23:54"
session: "134a3ec5-3dcd-4a68-baa3-40558e3637ff"
source: claude-mem
source_table: observations
source_ids: [5928, 5934, 5940, 5962]
---

# Dedicated health-check relay step in every workflow

Every `src/skf-*/` workflow ends in a ~20-line relay step, `src/<skill>/references/health-check.md`, whose only job is `nextStepFile: 'shared/health-check.md'`; the report/summary step before it sets `nextStepFile: 'health-check.md'` and closes with "The health-check step is the true terminal step — do not stop here even though the summary reads as final." The relay exists because when the "load shared/health-check.md" instruction was a trailing subsection of the user-facing report step, agents treated the summary as terminal and skipped the health check in three consecutive audit→update→export runs (issue #152, fixed in 0448046 across all 14 workflows after the user said "fix all 14"). Never fold the relay back into the report step or inline the chain as a subsection of it; in skf-create-skill `--batch` mode the report step loops back to `references/load-brief.md` and only chains to health-check after the final brief. `docs/workflows.md:462` still calls the relay `step-NN-health-check.md`, the filename from before d7861786 moved `steps-c/` to `references/`. Related: `memory/local-health-check-shim-reachability-test` (the test that enforces the shim) and `memory/no-completion-banner-before-health-check`.

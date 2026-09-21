---
created: "2026-04-11 00:04"
session: "f32fbc5c-d70a-4aea-bdca-82487706d2ea"
source: claude-mem
source_table: observations
source_ids: [5313, 5323]
---

# No workflow-complete banner before the health check

`src/shared/health-check.md` is the sole owner of the "Workflow complete." line, printed on each of its exit paths (clean run, submitted, queued, discarded). A `### Workflow Complete` banner in the report steps of update-skill, export-skill, create-stack-skill and analyze-source made assistants treat the report as terminal and stop before the chained health check ran (issue #107, fixed in 9d6fcf5). Report/summary steps must not emit completion language; each ends with the chain sentence "The health-check step is the true terminal step — do not stop here even though the report reads as final." Two residual strings still print "…workflow complete." inside an exit message — `src/skf-brief-skill/references/write-brief.md:198` and `src/skf-verify-stack/references/report.md:130` — each immediately followed by the chain sentence; do not copy that pattern into new steps. Related: `memory/health-check-relay-step-per-workflow`.

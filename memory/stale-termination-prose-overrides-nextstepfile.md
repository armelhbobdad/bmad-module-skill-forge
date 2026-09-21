---
created: "2026-04-06 23:10"
session: "d1acc926-ed6a-4036-83b0-2c1eaa8afc87"
source: claude-mem
source_table: observations
source_ids: [4483, 4484]
---

# Stale termination prose overrides a changed nextStepFile

Changing a step's chaining by editing its frontmatter `nextStepFile` is not enough: the same file usually carries termination prose elsewhere ("no nextStepFile", "This is the FINAL step", "End workflow. No further steps.") and those prominent rules override the later load instruction, so the LLM stops before the health check runs. After `nextStepFile` was added to the report/finalize steps of every workflow, seven files still said "no nextStepFile" in their rules, protocol and failure-metrics sections and had to be scrubbed; the wording now used is "The health-check step is the true terminal step — do not stop here even though the report reads as final." The trap is still live: `src/skf-create-skill/references/report.md:115` reads "End workflow. No further steps." while its frontmatter chains to `health-check.md`. `tools/validate-file-refs.js` only checks that `nextStepFile` paths resolve, not prose, so grep every termination sentence in a step file whenever its chaining changes. Related: `memory/no-completion-banner-before-health-check`.

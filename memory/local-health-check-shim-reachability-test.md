---
created: "2026-05-27 04:35"
session: "5dd7dbde-661e-40be-82f3-39d235cedb4a"
source: claude-mem
source_table: observations
source_ids: [13961, 13962, 13963, 13964]
---

# Local health-check.md shim required by chain reachability test

`test/test-skf-chain-reachability.py::test_next_step_files_resolve[<skill>]` resolves every `nextStepFile` relative to the step file, with `EXTERNAL_TARGETS = {"shared/health-check.md"}` (resolved from `src/`) as the sole exception. A workflow whose terminal step sets `nextStepFile: 'health-check.md'` therefore needs the local relay `src/<skill>/references/health-check.md` (itself `nextStepFile: 'shared/health-check.md'`), or the test fails with `<skill>: broken nextStepFile references: <step>.md → health-check.md (resolves to .../src/<skill>/references/health-check.md)` — hit when skf-campaign's step-11-maintenance.md shipped without the shim. Copy the ~24-line shim from any sibling skill (skf-export-skill's is the model), keep its frontmatter comment about `shared/` resolving from the SKF module root, and add a `Workflow Health Check | references/health-check.md` row to the SKILL.md Stages table. CONTRIBUTING.md's 'Adding a New Workflow Skill' section does not mention any of this; `npm run test:python` (part of the pre-commit `npm test`) is where it surfaces.

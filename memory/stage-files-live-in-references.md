---
created: "2026-05-15 13:01"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9457, 9464, 9505, 9522]
---

# Stage files live in references/ without numeric prefixes

Every workflow skill keeps its chained stage files next to its static reference docs in `src/skf-<name>/references/` under descriptive names (`resolve-target.md`, `compile.md`); order comes from frontmatter `nextStepFile` plus the SKILL.md Stages table, never from filename sort, and each SKILL.md Conventions block says so. The layout went `steps-c/step-NN-name.md` -> `stages/name.md` -> `references/name.md` in one day (commits 97406eb7 and d7861786, 2026-05-15, PR #305): numbered prefixes were dropped because BMad skill-quality principles recommend against them and a bmad-workflow-builder prepass mis-parsed `step-` names as missing files, and the intermediate `stages/` directory was rejected by the path-standards scanner as invented taxonomy. Two leftovers still mislead: CONTRIBUTING.md:102 claims step filenames must match `step-NN-<slug>.md`, and tools/validate-skills.js only inspects `steps-c/` or `steps/` (validate-skills.js:252), so its STEP-01/06/07 rules never run against `references/`; src/README.md and docs/architecture.md also carry a duplicated `references/` row from the rename. skf-campaign (added 2026-05-27) is the one skill using `references/step-NN-name.md` names, linted by test/test-skf-campaign-stepfiles.py. Do not reintroduce a `stages/` directory or numbered prefixes in the other skills.

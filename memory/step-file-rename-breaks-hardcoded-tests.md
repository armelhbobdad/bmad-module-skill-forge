---
created: "2026-04-17 19:23"
session: "270f281b-4c9c-4a74-b7ec-d10883b84e24"
source: claude-mem
source_table: observations
source_ids: [6170, 8157, 9489]
---

# Step-file renames break hardcoded test and validator paths

Step files live at `src/skf-*/references/<name>.md`, and their names are hardcoded in places that must move with any rename or addition: `stepFileChains` in `test/test-installation-components.js` (lines 189–326) lists every workflow's step and reference filenames for existence checks, `test/test-workflow-state.js` reads fixed paths such as `skf-verify-stack/references/report.md` and `synthesize.md` (lines 59–61, 131–132, 150, 188–189, 235), and `tools/validate-file-refs.js` resolves `<name>Data:` frontmatter keys relative to `references/`. The steps-c/ → references/ move (commit d7861786) hit this: the husky pre-commit hook blocked the commit with 102 test failures (`Missing step file: ...`) until both test files were updated in the same change. `tools/validate-skills.js` (lines 251–252, 478) still looks for `steps-c/` or `steps/`, so its STEP-01..STEP-07 filename rules are dormant for the current layout even though CONTRIBUTING.md still cites them. `CONTRIBUTING.md` 'Adding a New Workflow Skill' names none of these sites, so a rename needs `git mv`, the SKILL.md Stages table, the `nextStepFile` chain and both test files together.

---
created: "2026-03-28 00:24"
session: "e7113361-9c87-40bc-84ee-5635215965d2"
source: claude-mem
source_table: observations
source_ids: [2741, 2747, 2764, 2765]
---

# No mid-workflow entry in sequential step files

Every SKF workflow is entered only through its `SKILL.md`, which routes to `references/init.md`; each step then loads the next via its frontmatter `nextStepFile`, so no step file can be started on its own and there is no "begin at step N" path (a workflow's own resume router, such as campaign resume or AN's `continueFile`, is the only re-entry). In refine-architecture, `references/init.md` §3c also overwrites `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header, so any recovery must start from init regardless. A HALT or recovery message must therefore say "Re-run [RA] from the beginning" (as `references/compile.md` and `references/report.md` now do) — both "re-run from step 05" and "re-run from step 02" were shipped and neither is executable. When writing or reviewing HALT text in any workflow, never point the user at a step number.

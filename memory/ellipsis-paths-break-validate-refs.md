---
created: "2026-05-01 11:56"
session: "5bc16144-c3f0-47e8-831a-23395e5c40a5"
source: claude-mem
source_table: observations
source_ids: [8081, 8082]
---

# Ellipsis-abbreviated paths fail validate:refs

Writing an abbreviated path such as `{project-root}/_bmad/skf/...` or `{project-root}/src/...` in step-file prose makes `npm run validate:refs` (tools/validate-file-refs.js, run with `--strict` by `npm test` and `npm run quality`) fail: the `PROJECT_ROOT_REF` regex captures `skf/...`, the resolver maps it to `src/...`, and because `path.extname('src/...')` is `.` the entry is reported as `[BROKEN] {project-root}/_bmad/skf/... (line N)` / `Target not found: src/...`. It was hit in the quick-skill write step when prose restated the frontmatter `atomicWriteProbeOrder` in shortened form (that probe order now sits in src/skf-quick-skill/references/finalize.md:3-5). Always spell the full path in prose exactly as the frontmatter has it, e.g. `{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py` for the installed module and `{project-root}/src/shared/scripts/skf-atomic-write.py` for a dev checkout.

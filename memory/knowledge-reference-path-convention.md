---
created: "2026-04-09 13:14"
session: "c1c818a3-d210-4820-87e4-c747e698faa9"
source: claude-mem
source_table: observations
source_ids: [4994, 4996, 5011]
---

# Knowledge reference path convention in step files

Stage and reference files under `src/skf-*/references/` cite shared docs as bare backtick paths such as `knowledge/tool-resolution.md`, `knowledge/version-paths.md` and `shared/health-check.md`, never as markdown links with relative targets like `[..](../../knowledge/x.md)` and never with a `src/` prefix. Bare `knowledge/` and `shared/` paths resolve from the SKF module root (`src/` in dev, `{project-root}/_bmad/skf/` installed; the installer also copies both directories into each IDE's skills dir), which is stated as a "Module-level path exception" in only five SKILL.md files (audit, update, export, drop, rename) and in `src/shared/health-check.md`. Commit 3f68b8f6 converted 44 `../knowledge` link forms to this shape across 12 skills because the relative form renders and resolves differently across Claude Code, Cursor and the CLI; the tree now has dozens of bare refs and zero link forms, with a few `src/`-prefixed outliers left (`src/knowledge/provenance-tracking.md` in `src/skf-test-skill/references/init.md`, `src/shared/references/feasibility-report-schema.md` in `src/skf-create-stack-skill/references/detect-integrations.md`). `npm run validate:refs` passes on these bare paths, so a "dangling reference" finding for `knowledge/<file>.md` in an audit or quality report is a false positive, not a missing file.

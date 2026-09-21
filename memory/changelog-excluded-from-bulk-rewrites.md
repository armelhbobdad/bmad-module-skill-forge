---
created: "2026-05-15 13:33"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9482, 9483]
---

# CHANGELOG.md excluded from bulk path rewrites

A repo-wide regex rewrite of workflow step-file paths (the 2026-05-15 `steps-c/` → `stages/` move; step files now live under `src/skf-*/references/`) also rewrote historical release entries in CHANGELOG.md, turning `step-06-write` into `write` in three v1.x bullets, and had to be reverted with `git checkout HEAD -- CHANGELOG.md`. Released `## [X.Y.Z]` sections describe the tree as it was at publication and stay verbatim — those `step-06-write` bullets are still present in three released sections. The only hand edits the file takes are prose under `## [Unreleased]` and the post-cut reconciliation in `docs/_internal/RELEASING.md` § Cutting a Release. Exclude CHANGELOG.md from any sed/rg-replace sweep and check `git diff --stat` for it before committing a rename.

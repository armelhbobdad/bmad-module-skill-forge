---
created: "2026-05-15 13:30"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9473, 9474, 9476]
---

# .entire/ directory excluded from repo-wide rewrites

The repo root holds `.entire/` (the entire session-log tool's directory: ~1.8k files, ~600 MB under `.entire/metadata/`), of which only `.entire/.gitignore` and `.entire/settings.json` are tracked. The root `.gitignore` does not list it; instead `.entire/.gitignore` ignores `metadata/`, `logs/` and `tmp/`, so `git status` stays clean even after those files are modified. During the `steps-c/` → `stages/` rename a Python rewrite script that excluded only `.claude`, `.analysis`, `node_modules` and `_bmad-output` silently rewrote 35+ `.entire/` metadata and cache JSON files (up to 74 substitutions in one pre-prompt file); the second pass had to add `.entire` to its exclusion list. Any repo-wide `sed`/`grep`/`os.walk` rewrite must exclude `.entire/` explicitly (or iterate `git ls-files` instead), because git will not flag the damage.

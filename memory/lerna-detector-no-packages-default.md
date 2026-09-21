---
created: "2026-05-02 21:24"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: both
source_ids: [8361, 8362, 8364]
---

# Lerna detector must not default packages to packages/*

In `src/shared/scripts/skf-detect-workspaces.py`, `detect_lerna()` returns `None` when `lerna.json` has no `packages` field (or an empty list) so detection falls through to the npm-workspaces / pnpm-workspaces / generic-folders detectors. Lerna v5+ delegates to the package manager's workspaces config; the `["packages/*"]` default is Lerna v1/v2-only behaviour. The detector originally shipped that default, code review caught it before PR #280 merged, and `test_default_packages_glob_when_field_absent` was replaced by `test_absent_packages_field_falls_through_to_npm_detector` and `test_absent_packages_field_no_npm_workspaces_falls_through` in `test/test-skf-detect-workspaces.py`. Trap: the module docstring (line 18, "`packages` field optional, defaults to `packages/*`") was never updated and contradicts the code — do not restore the default to match it.

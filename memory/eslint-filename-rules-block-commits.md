---
created: "2026-04-18 01:00"
session: "5b036c01-e29f-424c-9435-246fb01ca986"
source: claude-mem
source_table: observations
source_ids: [6267, 6268]
---

# ESLint enforces kebab-case filenames and .yaml extension

`eslint.config.mjs` applies `unicorn.configs.recommended` tree-wide, so `unicorn/filename-case` (kebab-case) is on for every file except under `tools/**`, `test/**`, `src/**/scripts/**/*.js` and `.github/**/*.yaml`, and `yml/file-extension` is set to `error` with `extension: 'yaml'`, so any `.yml` file fails lint. Name new files kebab-case with `.yaml`, never `.yml` or uppercase/timestamped names. The gate is `npm run lint` = `eslint . --max-warnings=0` over the whole working tree, run by `npm test` and therefore by `.husky/pre-commit`, so an offending file blocks every commit — for tool-generated files (as `.playwright-mcp/*.yml` snapshots once did) the fix is adding the directory to both `.gitignore` and the `ignores` array in `eslint.config.mjs`, not renaming the file or disabling the rule. CONTRIBUTING.md mentions the hooks and "do not disable a rule" but never kebab-case or .yaml-not-.yml.

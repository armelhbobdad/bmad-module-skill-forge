---
created: "2026-04-08 23:14"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: observations
source_ids: [4829, 4831, 4832, 6274]
---

# npm test lints untracked generated files unless ignored by name

`npm test` and the husky pre-commit hook run `lint:md` (`markdownlint-cli2 "**/*.md"`) and `lint` (`eslint .`), whose ignore lists in `.markdownlint-cli2.yaml` and `eslint.config.mjs` are hand-kept rather than taken from `.gitignore`, so each tool-generated folder must be added by name to every list whose glob reaches it. Earlier, `MD034/no-bare-urls` under `skills/reports/` was fixed by adding `- skills/reports/**` to the markdownlint list, and `.playwright-mcp/*.yml` snapshots tripped `unicorn/filename-case` and `yml/file-extension` until `.playwright-mcp/**` joined the eslint list. eslint still lacks `skills/reports/**`: on 2026-10-15 verifier fixtures under `skills/reports/<skill>/quality-analysis/<ts>/verify-*/` failed with `Parsing error: 'import' and 'export' may appear only with 'sourceType: module'` and `Empty documents are forbidden` (`yml/no-empty-document`). Because `npm test` lints only after `test:python`, the hook then failed with `husky - pre-commit script failed (code 1)` after a 23m45s pytest pass, so keep verifier fixtures in the session scratchpad and run `npm run lint` before committing. iwe's `.iwe/claude/sessions/<id>.yaml` records are gitignored but not eslint-ignored (eslint has no dot-directory wildcard like markdownlint's `.*/**`), and a `#` in a session's `--title` or `--summary` is single-quoted, failing lint with `Strings must use doublequote  yml/quotes` on commits and on a baseline `npm test` of the main checkout. Until `.iwe/claude/**` is in the eslint list, keep `#` out of session titles and summaries (re-running `iwe internal claude session complete` keeps the first title), run `npx eslint --fix` on that record (only its quotes change), or run the suite in a clean `git worktree add --detach <scratch>/main-check origin/main`; never use `--no-verify`.

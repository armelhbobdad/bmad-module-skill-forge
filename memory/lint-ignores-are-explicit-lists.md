---
created: "2026-04-08 23:14"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: observations
source_ids: [4829, 4831, 4832, 6274]
---

# npm test lints untracked generated files unless ignored by name

`npm test` (and the husky pre-commit hook, which runs `npx lint-staged` and then `npm test`) runs `lint:md` = `markdownlint-cli2 "**/*.md"` and `lint` = eslint over the whole working tree, and neither derives its ignore list from `.gitignore`: the `ignores:` list in `.markdownlint-cli2.yaml` and the `ignores` array in `eslint.config.mjs` are hand-maintained. An untracked, gitignored output folder is therefore still linted. This failed the suite with `MD034/no-bare-urls` in `skills/reports/skf-export-skill/quality-analysis/.../enhancement-opportunities-analysis.md` until `- skills/reports/**` was added to `.markdownlint-cli2.yaml`, and Playwright MCP's `.playwright-mcp/*.yml` snapshots tripped `unicorn/filename-case` and `yml/file-extension` on full-repo `npm run lint` until `.playwright-mcp/**` was added to `eslint.config.mjs` (and `.gitignore`). Any new tool-generated directory that writes `.md`, `.yml`/`.yaml` or `.js` files must be added by name to each list whose glob reaches it — markdownlint already skips dot-directories via `.*/**`, `_bmad*/**` and `z*/**`, eslint's list has no such wildcard for dot-directories — or `npm test` and every commit break on the next run.

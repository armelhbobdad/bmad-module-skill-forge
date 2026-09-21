---
created: "2026-04-10 22:44"
session: "b944b768-4c95-4b30-9642-c834ee3be822"
source: claude-mem
source_table: session_summaries
source_ids: [1582]
---

# markdownlint ignores every dot-directory including .github

`.markdownlint-cli2.yaml` lists `.*/**` under `ignores` (line 10), so markdownlint-cli2 never lints markdown under any dot-directory — `.github/` (issue templates in `.github/ISSUE_TEMPLATE/*.md`, `CODE_OF_CONDUCT.md`), `.claude/`, `.iwe/` — even when the path is passed explicitly: `npx markdownlint-cli2 ".github/**/*.md"` reports `Linting: 0 file(s)`. That covers both `npm run lint:md` (`"**/*.md"`) and the lint-staged `*.md` pass in the husky pre-commit hook, so a clean commit says nothing about those files. It is a pre-existing limitation of the config rather than a sign the files pass; check edits there by hand or by running markdownlint-cli2 with a config that drops the glob. CONTRIBUTING.md:60 describes the hook without this caveat.

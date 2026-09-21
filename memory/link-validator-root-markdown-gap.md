---
created: "2026-04-23 03:51"
session: "efeaec80-90ac-4fd9-82e5-7b455d2b6485"
source: claude-mem
source_table: observations
source_ids: [6914]
---

# Link validator coverage gap for root markdown

Link validation covers only two trees: `tools/validate-doc-links.js` (`DOCS_ROOT = ../docs`) and `tools/validate-docs-links.js` (`docsDir = docs/`, source and built site) walk `docs/`, and `tools/validate-file-refs.js` walks `src/`; `npm run lint:md` sees `**/*.md` but markdownlint does not resolve links. So relative links and heading anchors in README.md, CONTRIBUTING.md and other root markdown — for example CONTRIBUTING.md's `docs/_internal/RELEASING.md#rollback-playbook` — are not CI-guarded, and renaming a heading in RELEASING.md breaks them silently. After touching a heading or file those root files point at, verify their links by hand (or add the root files to a validator's walk list).

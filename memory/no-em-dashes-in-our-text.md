---
created: "2026-09-28 13:15"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# No em dashes in anything we write

The user's rule, stated 2026-09-28 while approving lintlang issue #143: "We should just never use em-dash in our text." It covers every line we author: commit messages, PR and issue bodies, docs, code comments, strings shipped in skills (such as a `workflow_warnings[]` message or the `@Ferris SF` status block, whose em dashes were replaced for this reason), memory notes and replies. Use a colon, a comma, parentheses or a separate sentence instead. `npm run validate:em-dash` (`tools/validate-no-em-dash.js`, the `em-dash` CI job) enforces it: no em dash at all in `README.md`, `docs/` outside `docs/_internal/` and `website/`, and none in the lines or commit messages a branch adds anywhere else. Existing em dashes elsewhere, about 5,000 in `src/` alone, stay until someone edits those lines. The user chose to keep SKF's context-snippet format as it is (its `|IMPORTANT:` and `|key-types:` lines carry an em dash, and tests compare them byte for byte), so any line starting with a pipe followed directly by a key and a colon is exempt and the docs quote those lines verbatim; changing the snippet format is a separate decision.

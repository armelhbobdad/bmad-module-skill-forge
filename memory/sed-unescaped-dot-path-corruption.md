---
created: "2026-04-08 01:42"
session: "f5a35eb1-4a9b-4c50-8ded-0f515ef16231"
source: claude-mem
source_table: observations
source_ids: [4643, 4644, 4654, 4655, 4656]
---

# Unescaped-dot sed rewrite corrupting skf-*-skill cross-skill paths

Bulk-rewriting relative paths across `src/` with an unescaped sed pattern such as `s|../data/|../assets/|` also matches `ll/data/` inside `skf-export-skill/data/`, because the unescaped `.` matches any character; the result was `skf-export-ski../assets/managed-section-format.md`. `node tools/validate-file-refs.js --strict` (`npm run validate:refs`, part of `npm test` and the husky pre-commit) caught 5 broken refs with the `ski..` fingerprint in the drop-skill, rename-skill and update-skill step files plus 2 more in prose that the validator does not scan. Every `src/skf-*-skill/` directory name ends in `skill`, and cross-skill refs like `skf-export-skill/assets/managed-section-format.md` and `skf-create-skill/references/` still exist, so the same corruption recurs on any future layout move. Escape the dots (`\.\./data/`) or use a fixed-string replacement, then run `npm run validate:refs` and `grep -rn 'ski\.\.' src/` for the prose hits.

---
created: "2026-04-25 04:56"
session: "8c30e5aa-9220-4ff5-b7b5-41da9b67d186"
source: claude-mem
source_table: observations
source_ids: [7486, 7493, 7499]
---

# Link checking of underscore-prefixed docs/ paths is split across validators

Underscore-prefixed paths in `docs/` (`docs/_internal/`, `docs/_data/`) are outside the published site and `llms-full.txt` (see "Where tracked-but-unpublished docs live"; `tools/build-docs.js` `shouldExcludeFromLlm()` returns true when any path part starts with `_`). Link checking of those files is split: `tools/validate-doc-links.js` (`npm run docs:validate-links`) and `tools/fix-doc-links.js` skip `_` entries in their walker (`if (entry.name.startsWith('_')) continue`), but `tools/validate-docs-links.js` (`npm run validate:docs-links`, the one inside `npm run quality`) walks every `.md` under `docs/` in its source pass, so a dead relative `.md` link in `docs/_internal/RELEASING.md` does fail CI (one was fixed in 8f00bd92). The built-site pass cannot see those pages at all, so anchors and routes inside `_internal` files are only ever checked by hand.

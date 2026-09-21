---
created: "2026-04-18 00:59"
session: "5b036c01-e29f-424c-9435-246fb01ca986"
source: claude-mem
source_table: session_summaries
source_ids: [1871]
---

# npmjs.com 403 on scripted link checks

`curl -s -o /dev/null -w '%{http_code}' https://www.npmjs.com/package/bmad-module-skill-forge` returns `403` even though the package page exists (bot protection in front of npmjs.com; a browser User-Agent does not help; re-verified 2026-09-21). The repo's own checkers never touch external URLs — `tools/validate-docs-links.js` skips them via its `EXTERNAL` regex and `tools/validate-doc-links.js` (run by `tools/build-docs.js`) only matches site-relative `/...` links — so this only bites ad-hoc reachability scripts over README/docs links. Treat a 403 from `www.npmjs.com/package/...` as a false positive, not a broken link, and confirm the package with `npm view <package> version` instead.

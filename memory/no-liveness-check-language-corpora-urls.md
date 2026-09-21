---
created: "2026-06-03 13:36"
session: "56051077-ffb7-41ac-a86a-8e9182d7c6a8"
source: claude-mem
source_table: session_summaries
source_ids: [3511, 3513, 3521]
---

# No liveness check for language-corpora URLs

The 17 URLs in `src/shared/data/language-corpora.json` (rust, python, go, typescript, javascript, ruby) were verified HTTP 200 by hand with `curl` once, in June 2026; the file's `_comment` records only that they "were verified live". No CI job or test re-checks them: `test/test-skf-language-corpora.py` is a static lookup over the JSON, `skf-language-corpora.py` makes no network calls, and a liveness check was kept out of the suite on purpose so `npm run test:python` stays offline. When a language doc site moves, nothing in the repo will fail. When editing the registry, re-curl every URL yourself rather than adding a network-dependent test.

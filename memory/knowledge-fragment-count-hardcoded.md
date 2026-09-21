---
created: "2026-03-14 14:03"
session: "cdec0d4f-5790-4bdf-b019-c0dee4ca15d1"
source: claude-mem
source_table: observations
source_ids: [1010, 1016, 2266, 4274]
---

# Knowledge fragment count is hardcoded in three places

Adding a row to `src/knowledge/skf-knowledge-index.csv` makes `npm run test:knowledge` fail with "❌ Knowledge base tests failed" because `test/test-knowledge-base.js:91` asserts an exact count: `assert(records.length === 15, 'skf-knowledge-index.csv has 15 fragment records', ...)`. The same literal is quoted in `docs/architecture.md:185` ("14 knowledge fragments + overview.md index" — the CSV counts `overview.md` as a record, so 14 + 1 = 15) and `test/README.md:9` ("15-entry knowledge base"). `CONTRIBUTING.md` "Adding Knowledge Fragments" only says to register the fragment in `src/knowledge/overview.md` and does not mention these counts, so bump all three in the same commit as the CSV row. `npm test` chains `test:knowledge` with `&&`, so the failed assertion blocks the rest of the suite.

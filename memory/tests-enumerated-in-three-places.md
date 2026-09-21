---
created: "2026-04-08 00:46"
session: "7cba3f62-fa07-467b-9eac-6fc6674d6c0b"
source: claude-mem
source_table: observations
source_ids: [4611, 4614, 4629]
---

# Tests and validators are enumerated in three places

A test or validator runs only where it is listed, and there are three independent lists: the `test` script and the `quality` script in `package.json`, and the per-step list in `.github/workflows/quality.yaml`, which invokes `npm run test:schemas`, `npm run test:python`, `npm run validate:refs`, … one by one and never calls `npm test` or `npm run quality`. They already diverge: `docs:validate-drift` is in `quality` but in neither `test` nor quality.yaml. Past gaps: `test/test-workflow-state.js` existed with no script wiring at all, and `validate:skills` / `validate:refs` ran in CI but not in local `npm test`. When adding a `test:*` or `validate:*` script, add it to all three; CONTRIBUTING.md's "the same steps run in quality.yaml" is an intent, not something enforced.

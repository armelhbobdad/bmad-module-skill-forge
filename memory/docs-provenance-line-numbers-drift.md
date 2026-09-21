---
created: "2026-04-12 02:45"
session: "75944ea2-3854-4eae-93b8-a0c1c8c67f90"
source: claude-mem
source_table: observations
source_ids: [5822, 5823]
---

# Provenance line numbers in docs go stale on every oh-my-skills re-pin

`README.md`, `docs/concepts.md`, `docs/examples.md`, `docs/skill-model.md`, `docs/why-skf.md`, `docs/index.md`, `docs/getting-started.md` and `docs/how-it-works.md` quote a real provenance citation for `cognee.search()` (`cognee/api/v1/search/search.py:L26` or `:L27`) as the flagship example, and the line moves whenever `oms-cognee` is re-pinned in oh-my-skills (L26 became L27 at the v0.5.8 re-pin and stayed L27 at the v1.0.0 pin, commit `3c048aa4`). `tools/validate-docs-drift.js` (`npm run docs:validate-drift`) only checks version strings and commit SHAs against `docs/_data/pinned.yaml`, so a stale line number passes CI; as of v2.1.0 the docs pages say L26 while README.md and the pinned `oms-cognee/1.0.0/oms-cognee/SKILL.md` say L27. After any re-pin, grep `search.py:L` across README.md and docs/ and align every citation to the pinned SKILL.md. The `[cognee]` link in docs/concepts.md must point at `github.com/topoteretes/cognee`, not the oh-my-skills repo.

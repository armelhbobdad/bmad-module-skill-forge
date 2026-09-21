---
created: "2026-06-03 22:17"
session: "68c5ada7-6915-4d75-b231-06c23d6d3b7b"
source: claude-mem
source_table: observations
source_ids: [14926, 14929, 15148]
---

# Docs pages carry no version stamps, PR numbers or queue fingerprints

Prose under docs/ must not carry inline per-feature version stamps such as "(v1.2.0+)" or PR/issue numbers — CHANGELOG.md is the "when added" surface and docs describe current behaviour. Commit f276e58e ("docs(workflows): drop inline version-stamp markers", 2026-05-01) stripped the last three from docs/workflows.md because they "duplicate the CHANGELOG, drift silently across releases", and that commit message is the only place the rule is written; CONTRIBUTING.md does not mention it. Likewise skill prose under src/ must not mention health-check fingerprints (`fp-XXXXXXX`, src/shared/health-check.md:95), `improvement-queue/` paths or other `_bmad-output/` author notes — CONTRIBUTING.md:70 says the same only for PR bodies. The mechanical gates on a docs change are `npm run lint:md`, `npm run validate:refs` (strict: broken refs and absolute-path leaks) and `npm run docs:validate-drift`; the stamp and fingerprint checks are by eye, so grep the diff for `(v[0-9]`, `#[0-9]{2,}` and `fp-` before committing.

---
created: "2026-03-26 01:25"
session: "39ca4974-63db-4263-bd83-7692ad34d5a9"
source: claude-mem
source_table: observations
source_ids: [2451, 2478, 4421, 14096]
---

# Workflow list and count hardcoded across tests and docs

Adding a workflow silently under-tests it unless `workflowNames` (test/test-installation-components.js lines 151–166) and `stepFileChains` (lines 189–326) are extended — omission fails nothing, and at v2.1.0 `skf-campaign` is missing from both while `src/module-help.csv` and `docs/architecture.md:178` count it as the 15th workflow. The count itself is repeated by hand and already disagrees: `README.md:155` and `docs/workflows.md:462` say 15, `src/knowledge/overview.md:9` says 14, `test/README.md:8` says 14 skills. No validator derives the list from `src/skf-*/`, and `CONTRIBUTING.md` 'Adding a New Workflow Skill' names only `src/module-help.csv` and `docs/workflows.md` as registration sites. When adding or dropping a workflow, update the two test arrays, module-help.csv, README.md, docs/workflows.md, docs/architecture.md, src/knowledge/overview.md, test/README.md and the CHANGELOG entry in the same change.

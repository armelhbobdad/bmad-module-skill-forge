---
created: "2026-03-25 22:05"
session: "39ca4974-63db-4263-bd83-7692ad34d5a9"
source: claude-mem
source_table: observations
source_ids: [2342, 2367, 2322]
---

# ccc_index.status enum mismatch between setup writer and CCC readers

`skf-setup` writes `ccc_index.status` into forge-tier.yaml as one of `fresh|created|none|failed|skipped` (`src/skf-setup/references/ccc-index.md`, `write-config.md`) and never `stale` — a stale index is re-indexed in that same step and comes out `created` or `failed`. But `src/skf-create-stack-skill/references/detect-integrations.md` gates CCC semantic augmentation on status `"fresh"` or `"stale"`, and `src/knowledge/ccc-bridge.md` states availability the same way, so a project whose index was built in the current setup run (status `created`, the normal first-run state) silently gets no CCC augmentation in create-stack-skill. `src/skf-create-skill/references/sub/ccc-discover.md` is the correct reader (`fresh`/`created` proceed, `none`/`failed` lazy-index). The writer and the stack-skill reader were written with contradictory sets and never reconciled; when touching either side, grep every `ccc_index.status` consumer and align the enum.

---
created: "2026-03-26 21:55"
session: "f4884127-3efa-4c58-ab72-a5bd362cbba6"
source: claude-mem
source_table: observations
source_ids: [2683]
---

# Stack skill source_authority floor is community, never hardcoded internal

A stack skill's `metadata.json` `source_authority` must never be hardcoded `internal`; it takes the lowest authority among its constituent skills because a composite cannot be more authoritative than its parts. The original fix in `create-stack-skill` (March 2026) defined the floor as: `community` if any constituent is `community`, `internal` only when every constituent is `internal`, `official` only when all are `official`. The current wording in `src/skf-create-stack-skill/references/generate-output.md:165` says 'the lowest authority among constituent skills (official > community > internal)' — that parenthetical, added in commit c455d097, reads as if `internal` were the floor, which would turn a `[community, internal]` stack into `internal`, the opposite of the fix. Before relying on or editing this line, resolve which ordering is meant; the per-skill field semantics (default `community`, `official` only for the library maintainer, forced `community` for docs-only T3 skills) live in `src/skf-brief-skill/assets/skill-brief-schema.md:27-34`.

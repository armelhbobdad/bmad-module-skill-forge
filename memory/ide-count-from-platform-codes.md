---
created: "2026-04-26 10:39"
session: "2a66cf80-107e-443d-9038-c8f0fa1171f6"
source: claude-mem
source_table: observations
source_ids: [7542, 7554, 14084, 14097]
---

# IDE count in docs comes from platform-codes.yaml

The "N supported IDEs" figure in docs is the number of platform entries in `tools/cli/lib/platform-codes.yaml` (23 at v2.1.0; `grep -c '^  [a-z-]*:$' tools/cli/lib/platform-codes.yaml`), never a row count of the IDE mapping table in `src/skf-export-skill/assets/managed-section-format.md`, which lists the same 23 plus catch-all `other` and "(any unknown value)" rows and therefore over-counts. `docs/bmad-synergy.md` drifted twice for exactly this reason (a docs pass counted table rows and rewrote 23/16/21 as 24/17/22, later corrected back), and its line 12 still links to that table "for the full list", so the trap is live. The arithmetic behind the prose: 23 total = 2 dedicated-context-file IDEs (claude-code -> CLAUDE.md, cursor -> .cursorrules) + 21 AGENTS.md IDEs; with 7 named examples that leaves "16 others". Places that carry the number today: `docs/bmad-synergy.md:12` and `:206`, `docs/skill-model.md:310`. No test asserts the count.

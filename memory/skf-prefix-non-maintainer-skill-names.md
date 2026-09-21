---
created: "2026-04-10 20:49"
session: "cdf5540a-b530-4d53-a96f-717d432c7393"
source: claude-mem
source_table: observations
source_ids: [5238, 5239, 5240]
---

# skf- prefix rule for non-maintainer skill names in brief-skill

In `skf-brief-skill`'s name suggestion (`src/skf-brief-skill/references/gather-intent.md` §6 "Derive Skill Name"), when `source_authority` is not `official` (maintainer) the proposed name must carry an `skf-` prefix — `skf-cognee`, prefix form, not the `cognee-skf-community` suffix that `docs/examples.md` Scenario E still shows — as a collision hedge against a later official skill; only the maintainer is encouraged to use the bare name. User: "during the brief skill, if the source authority is not maintainer, the suggested name should start with skf-*. For example (skf-cognee), Only mainter should be encourage to use cognee without prefix." As of v2.1.0 §6 still proposes a bare name with no `source_authority` check (the only authority-aware naming is the collision-alternate suffix `{name}-{source_authority}` at gather-intent.md:306, which never fires for community), so the rule is unimplemented; implementing it means changing gather-intent.md §6 and docs/examples.md Scenario E together.

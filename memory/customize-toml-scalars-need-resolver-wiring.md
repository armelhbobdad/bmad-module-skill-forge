---
created: "2026-05-15 21:53"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9759, 9828, 14682, 14700]
---

# customize.toml scalars are inert until wired through the resolver

A value in `src/skf-*/customize.toml` only takes effect if the skill's `SKILL.md` "On Activation" runs `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow` **and** the reference files read the resolved `{workflow.X}` variable — add the scalar, the resolver step and the step-file rewiring as one unit, or the new scalar silently does nothing (`skf-campaign` shipped with no `customize.toml` and hardcoded `forge-data/_campaign/` paths until all three landed together in commit `8f8927d2`). For the same reason no `src/skf-*/customize.toml` carries a `RESERVED` or commented-out placeholder key: skf-setup's `ccc_staleness_threshold_hours` and `additional_ccc_exclusions` were deleted because no stage consumed them (the threshold comes from `forge-tier.yaml`; `skf-merge-ccc-exclusions.py` has no `--additional-exclusions` flag) and a user override silently no-oped — wire and document the consumer in the same change or leave the key out. The resolver (installed under gitignored `_bmad/scripts/`, needs Python 3.11+ for stdlib `tomllib`, exits 3 with `error: Python 3.11+ is required` otherwise) merges `{skill-root}/customize.toml` → `_bmad/custom/<skill>.toml` (team, committed) → `_bmad/custom/<skill>.user.toml` (personal, gitignored): scalars override, tables deep-merge, arrays of tables merge by key only when every item carries the same `code` or `id` field, everything else appends. There is no removal mechanism — an override can replace or append base items but never delete one. `CONTRIBUTING.md` "Adding a New Workflow Skill" and `docs/campaign.md` (the only doc describing the three layers) do not mention any of this, so copy the On Activation block from `src/skf-quick-skill/SKILL.md` when creating a skill.

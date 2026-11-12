---
created: "2026-05-15 21:53"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9759, 9828, 14682, 14700]
---

# customize.toml scalars are inert until wired through the resolver

A value in `src/skf-*/customize.toml` does nothing unless the skill's `SKILL.md` On Activation runs `uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow` and the step files read the resolved `{workflow.X}`, so the scalar, resolver step and rewiring land as one unit (as in `skf-campaign`'s commit `8f8927d2`). For the same reason no customize.toml carries a `RESERVED` or commented-out placeholder key: skf-setup's `ccc_staleness_threshold_hours` and `additional_ccc_exclusions` were deleted because no stage consumed them and a user override silently no-oped. The resolver (SKF's `skf-resolve-customization.py`, running BMAD core's gitignored `_bmad/scripts/resolve_customization.py`, which exits 3 with `error: Python 3.11+ is required` without stdlib `tomllib`) merges `{skill-root}/customize.toml` → `_bmad/custom/<skill>.toml` (team, committed) → `_bmad/custom/<skill>.user.toml` (personal, gitignored). Scalars override, tables deep-merge, arrays of tables merge by key only when every item carries the same `code` or `id` field, everything else appends, and `_merge_arrays` in `_bmad/scripts/config_utils.py` never deletes a base item. For `persistent_facts` only, SKF adds a removal the maintainer chose on 2026-10-02 ("`!` entry everywhere (Recommended)"): an entry prefixed `!` drops each earlier equal entry and loads nothing, so `persistent_facts = ["!file:{project-root}/**/project-context.md"]` in `_bmad/custom/<skill>.toml` turns the bundled default off. Every SKILL.md On Activation but skf-setup's and `load_facts` in `src/skf-campaign/scripts/campaign-render-kickoff.py` honour it, `DROP_OVERRIDE` in `test/test-skf-customize-surface.py` pins it, and `docs/workflows.md` and `docs/campaign.md` document it, but `CONTRIBUTING.md` "Adding a New Workflow Skill" omits all this wiring, so copy the On Activation block from `src/skf-quick-skill/SKILL.md`.

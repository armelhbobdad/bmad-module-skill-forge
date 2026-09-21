---
created: "2026-03-25 20:43"
session: "0771053e-7d8d-4cca-9f95-e05ce34e7621"
source: claude-mem
source_table: observations
source_ids: [2288, 2292, 13252, 13255]
---

# docs/ restates src/ architecture and drifts silently

The public docs restate the tier/tool/pipeline architecture independently of `src/`: the per-workflow `Key Steps:` lines in `docs/workflows.md` (e.g. line 58 for Create Skill), Capability Tiers in `docs/concepts.md`, the tool table in `docs/how-it-works.md`, metadata fields in `docs/skill-model.md`, tier advice in `docs/examples.md`. No validator compares them with `src/`: `docs:validate-drift` checks only pinned versions and commit SHAs, `validate:docs-links` and `validate:refs` check only links and file references. This bit twice: the Forge+ tier landed in three commits while docs/ still described Quick → Forge → Deep, and the step 5a Doc Sources / Doc Drift additions updated the SKILL.md stages tables but left `docs/workflows.md` and `docs/skill-model.md` untouched until the Epic 1 retro. When adding or renaming a tier, tool bridge, pipeline step or shared script, grep `docs/` for the old and new names in the same change.

---
created: "2026-03-14 23:32"
session: "3e092e0b-2af9-43bb-9bd7-1c7e2eb7e709"
source: claude-mem
source_table: observations
source_ids: [1221, 1222, 1223, 1224, 1241, 1242, 1253]
---

# Cross-step field-name drift between prose step files

Workflow steps under `src/skf-*/references/*.md` are prose, so nothing checks that the field a producer step writes is the field a consumer step reads. The v1.0.0 pre-release audit (2026-03-14) found five silent mismatches this way: `forge-tier.yaml` was written with `tier` while test-skill read `detected_tier` and update-skill read `forge_tier` (tier detection silently yielded null); `skillDir` was read by the external-validators step but never written to the test-report frontmatter (so `npx skill-check check {skillDir}` ran with an empty path); quick-skill's metadata.json used `generated_date`/`confidence` while export-skill validated `generation_date`/`confidence_tier`; brief-skill collected `doc_urls` that the YAML template dropped. Every schema also lives twice, in an `assets/` or `templates/` file (e.g. `src/skf-quick-skill/assets/skill-template.md`, `src/skf-test-skill/templates/test-report-template.md`) and copied into the step instructions, so both must change together. `test/test-workflow-state.js` statically checks only VS, RA and compose-mode; when renaming a field, grep every skill's `references/`, `assets/` and `templates/` plus any `src/shared/scripts/` helper that emits or validates it.

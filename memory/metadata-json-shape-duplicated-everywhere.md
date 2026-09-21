---
created: "2026-03-26 12:47"
session: "4adb56d2-d7c4-423d-ac34-5e35ad4d3a4c"
source: claude-mem
source_table: observations
source_ids: [2627, 2636, 2670, 2675, 2680]
---

# metadata.json shape is duplicated across templates, knowledge and scripts

There is no schema file for a skill's `metadata.json` (nothing under `src/shared/scripts/schemas/`); the shape is copied inline in `src/skf-create-skill/assets/skill-sections.md` § metadata.json Structure, `src/skf-quick-skill/assets/skill-template.md` § metadata.json Format (named canonical by quick-skill `compile.md` §4), `src/skf-create-stack-skill/assets/stack-skill-template.md`, `src/knowledge/zero-hallucination.md`, `src/knowledge/confidence-tiers.md` and `docs/skill-model.md`, and hard-coded again in `src/shared/scripts/skf-render-quick-metadata.py`, `skf-render-metadata-stats.py`, `skf-validate-output.py` and `src/skf-test-skill/scripts/check-metadata-coherence.py`. No test ties the copies together, so a field added to one silently drifts the others: on 2026-03-26 three review passes in one day found Title-case `"T1-low"` keys in the stack template, `stats.confidence_t1*` in docs, a duplicate `"skill_type"` key that produced invalid JSON, and a `0.1.0` version fallback where every other producer uses `1.0.0`; in May the quick-skill template lacked the `provenance.language_hint`/`scope_hint` block the compile step had gained. The agreed shape (Schema B) is a top-level `confidence_distribution` keyed `t1`, `t1_low`, `t2`, `t3`, with `stats` holding only export/coverage counts and the version fallback `"1.0.0"`; `coverage-check.md` §4b still wrongly says the distribution lives under `stats`. Any metadata field change is applied to every copy above, template and script alike.

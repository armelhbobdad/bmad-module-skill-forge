---
created: "2026-03-13 02:43"
session: "0306101c-7128-438c-9e26-e94174c24274"
source: claude-mem
source_table: both
source_ids: [960, 966, 1225, 1252]
---

# Export gate is stricter than producer-side metadata validation

`skf-validate-output.py --export-gate` (run by `skf-export-skill/references/load-skill.md` §2) is the terminal authority on `metadata.json`: `validate_metadata_export_gate()` hard-fails on a missing `name`, `version`, `skill_type`, `source_authority`, `generation_date`, `confidence_tier` or `exports` array and on enum drift (`skill_type` ∈ single/stack, `source_authority` ∈ official/internal/community, `confidence_tier` ∈ Quick/Forge/Forge+/Deep), halting with "**Export cannot proceed.** Missing or invalid: …". The same script without the flag (`validate_metadata_json()`, what quick-skill and stack-skill run at their validate step) requires only `name`/`version`/`source_authority`/`language`/`generation_date` and never checks `skill_type` or `exports`, so a producer template can pass its own validation and still fail every export. That is how issue #13 happened: create-skill and quick-skill emitted `forge_tier`/`generated_at`/`skill_name`/`confidence`/`exports_count`/`generated_date` and every Quick-tier skill failed at export. When a producer template and the gate disagree, change the producer, and check any new field against `validate_metadata_export_gate()` and `src/skf-create-skill/assets/skill-sections.md` § metadata.json Structure. There is no JSON Schema file for metadata.json under `src/shared/scripts/schemas/`; the gate function is the schema.

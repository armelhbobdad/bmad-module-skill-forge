---
created: "2026-05-25 01:58"
session: "2c6e0de3-b439-4bf4-95e8-30882567bf2a"
source: claude-mem
source_table: observations
source_ids: [12290, 12294]
---

# scope.type enum enforcement points change in lockstep

`scope.type` is validated deterministically, so adding a scope type means editing every enforcement point in the same change: `VALID_SCOPE_TYPES` in `src/shared/scripts/skf-emit-brief-result-envelope.py`, `skf-validate-brief-inputs.py` and `skf-write-skill-brief.py`; the `enum` in `src/shared/scripts/schemas/skill-brief.v1.json` (three places) and `skf-brief-result-envelope.v1.json`; the heuristic ladder in `skf-recommend-scope-type.py`; the tests under `test/` that enumerate the values; and the prose lists in `src/skf-brief-skill/assets/skill-brief-schema.md`, `src/skf-analyze-source/assets/skill-brief-schema.md` and `src/skf-analyze-source/references/recommend.md`. Editing only the markdown schema looks complete, but the JSON schema and the scripts drive the brief-validation gate and will reject every brief that uses the new type. The prose lists drifted before (identify-units listed 3 types, recommend 4, the schema 6), so grep for the full current list (`full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app`, `docs-only`) rather than trusting any one file.

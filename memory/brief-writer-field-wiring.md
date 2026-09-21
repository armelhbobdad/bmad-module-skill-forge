---
created: "2026-05-24 15:51"
session: "f245361b-e19a-4d81-814f-cdf55958be4c"
source: claude-mem
source_table: observations
source_ids: [11759, 11761, 11768, 11772]
---

# Brief writer fixed key set requires six-point field wiring

`src/shared/scripts/skf-write-skill-brief.py` `assemble_brief()` rebuilds `skill-brief.yaml` from an explicit key set rather than passing its input through, so a schema field the writer does not know about is silently dropped on every ratify or re-write — issue #385 lost `target_ref`, `source_ref`, `scope.tier_a_include` and `scope.amendments` (the monorepo tag escape hatch, the coverage-denominator include list and the post-authoring audit log) on both the interactive §3.1a `[R]` path and headless `from_brief`. Adding any field to `src/shared/scripts/schemas/skill-brief.v1.json` therefore means touching `validate_context`, `assemble_brief`, `_FLAT_SCOPE_KEYS`/`flat_to_nested` (scope-nested fields only; other top-level flat keys already pass through), both hydration lists in `src/skf-brief-skill/references/gather-intent.md` (§3.1a and the §8 GATE `from_brief` route), the `write-brief.md` §3 flat template, and round-trip tests in `test/test-skf-write-skill-brief.py`. `skf-validate-brief-schema.py` cannot catch the drop because the shrunken brief is still valid; only a round-trip test does.

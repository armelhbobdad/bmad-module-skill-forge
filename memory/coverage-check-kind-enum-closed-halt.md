---
created: "2026-05-24 11:19"
session: "8614f40a-7bf6-4911-8fad-b9036c883f2a"
source: claude-mem
source_table: observations
source_ids: [11577, 11581, 11589, 11591]
---

# Coverage-check kind enum is closed and HALTs on unlisted kinds

`skf-test-skill` coverage-check §1a rejects any inventory export whose `kind` is outside a closed enum and HALTs with `coverage-check: subagent inventory failed schema validation — …` when `valid` is false; the HALT is mandatory and must not be downgraded to a warning. The enum is `function|class|type|constant|hook|interface|method|struct|enum|trait|macro|adapter` and lives in two places that must stay identical: `src/skf-test-skill/references/coverage-check.md` §1a and `VALID_KINDS` in `src/skf-test-skill/scripts/validate-inventory.py` (covered by `test/test-skf-validate-inventory.py`). It was `function|class|type|constant|hook|interface|method` until Rust and stack skills documenting `#[tauri::command]` / `generate_handler!` macros, `struct`/`enum`/`trait` items and scaffold `adapter`s forced a manual override of the HALT (PR #379). When SKF starts documenting a new language, add its public-API item kinds to both sites explicitly instead of overriding the HALT; only `method` is special-cased downstream (excluded from the barrel count in §2c), so new kinds need no further wiring.

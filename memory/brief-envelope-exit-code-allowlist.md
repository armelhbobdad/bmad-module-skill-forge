---
created: "2026-05-02 22:00"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: session_summaries
source_ids: [2467]
---

# Brief result envelope validator duplicates its exit-code and key contract in three places

`validate()` in `src/shared/scripts/skf-emit-brief-result-envelope.py` checks `exit_code` against a hand-typed literal set `{0, 2, 3, 4, 5, 6}` that is not derived from `HALT_TO_EXIT` and is duplicated again as the `enum` in `src/shared/scripts/schemas/skf-brief-result-envelope.v1.json`; validate() never loads that JSON. When skf-brief-skill gained the `[X] Cancel` exit code 6 (c44cc55d), the first user-cancelled envelope failed the emit → validate round trip with `exit_code invalid: 6` until the set was widened in 6fb5df20. The same file treats `KEY_ORDER` as a closed set — validate() rejects both missing and unexpected keys and the schema has `additionalProperties: false` — so adding a halt reason or a field means touching `HALT_TO_EXIT`/the literal allowlist/the schema enum, or `KEY_ORDER`/a `VALID_*` constant/the schema `required` list, plus every fixture in `test/test-skf-emit-brief-result-envelope.py`. The Analyze emitter `skf-emit-result-envelope.py` assembles dynamically with no KEY_ORDER, so a change there is not a template for this one.

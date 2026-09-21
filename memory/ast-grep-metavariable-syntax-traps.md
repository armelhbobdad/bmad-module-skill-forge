---
created: "2026-03-15 19:32"
session: "ef58bc7e-dfb1-4b7c-ba9e-1ecebd232429"
source: claude-mem
source_table: both
source_ids: [1330]
---

# ast-grep metavariable syntax traps that match silently

In ast-grep patterns the variadic capture is `$$$PARAMS` (three dollars); `$$PARAMS` is a single-node capture, so `def $NAME($$PARAMS)` silently matches only one-parameter functions (verified on ast-grep 0.45.3: four defs in a fixture, one match). A metavariable cannot be glued to a literal, so `def _$NAME($$$PARAMS)` matches nothing and only prints `Warning: Pattern contains an ERROR node and may cause unexpected results.`; exclude private names with `constraints: NAME: regex: '^[^_]'` instead, which is why every recipe in `src/skf-create-skill/references/extraction-patterns.md` carries that constraint rather than a `_`-prefixed pattern. A Rust pattern ending in `-> $RET` skips unit-returning functions, which is why the Rust recipe wraps both forms in `any:` (and per Known Limitation #8 that recipe itself returns zero on 0.42.x, so the `rg '^\s*pub fn '` sweep is the working path). All three failures surface as zero matches, which the extraction step reads as "no exports" — test any new YAML recipe against a small fixture before committing it.

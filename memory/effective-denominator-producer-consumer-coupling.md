---
created: "2026-04-11 20:50"
session: "ad96750b-7675-4934-850f-e85558a08369"
source: claude-mem
source_table: observations
source_ids: [5631, 5638, 11960, 12000]
---

# effective_denominator producer/consumer coupling

skf-test-skill resolves a curated-scope coverage denominator by preferring the stored scalar `metadata.json.stats.effective_denominator` (src/skf-test-skill/references/source-access-protocol.md, stratified-scope resolution order step 1) and only re-derives from the brief's `scope.tier_a_include` / `scope.include` as a fallback or as the deflation-guard comparison; that scalar is written by skf-create-skill's compile step (src/skf-create-skill/references/compile.md, the `effective_denominator` payload rule). Any change to how the denominator is derived — a new brief scope lever, a different counting unit — must therefore land on both sides in the same commit. The first #134 fix (ad7105b2) touched only test-skill and was "effectively dead weight" until ff1dc725 taught the compile writer to honor `tier_a_include`; a month later the producer emitted a barrel-reachable named-export count (263) while the test-side deflation guard re-derived the raw `scope.include` file union (475), so every run raised a false `denominator deflation` gap until compile.md pinned the counting unit to what coverage-check.md §2c counts. When editing either file, edit the other and confirm the guard's re-derivation uses the same unit the writer counts.

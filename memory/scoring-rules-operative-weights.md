---
created: "2026-03-26 12:41"
session: "4adb56d2-d7c4-423d-ac34-5e35ad4d3a4c"
source: claude-mem
source_table: observations
source_ids: [2612, 2619, 2650, 2671]
---

# scoring-rules.md and compute-score.py are the operative scoring weights

The test-skill scoring weights live in `src/skf-test-skill/references/scoring-rules.md` and are mirrored verbatim in `src/skf-test-skill/scripts/compute-score.py` (`CONTEXTUAL_WEIGHTS` 36/22/14/18/10, `NAIVE_WEIGHTS` 45/25/20/0/10, External Validation redistributed when skill-check and tessl are absent, Quick tier zeroing Signature Accuracy and Type Coverage regardless of naive/contextual mode). `src/knowledge/progressive-capability.md`, `docs/verifying-a-skill.md` and `docs/workflows.md` only restate those numbers. When they disagree, rewrite the mirror to match scoring-rules.md and the script, never the reverse: the knowledge fragment has drifted three times (Forge listed as 40/25/15/20 with no External Validation, Quick listed as 45/25/20/10 as if AST categories were scored, and Naive mode conflated with Quick tier) and each time the fix was to bring it back to scoring-rules.md.

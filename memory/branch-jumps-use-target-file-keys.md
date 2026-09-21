---
created: "2026-05-21 14:54"
session: "c28d21cc-4bc1-470b-80ac-f37b8f270bd6"
source: claude-mem
source_table: session_summaries
source_ids: [2966, 2967]
---

# Conditional jumps use *TargetFile keys, not nextStepFile

In skf-brief-skill the ratify path (an existing skill-brief.yaml reviewed in place) jumps from references/gather-intent.md straight to confirm-brief.md through a dedicated frontmatter key `ratifyTargetFile: 'confirm-brief.md'`, while `nextStepFile` stays `analyze-target.md`; step-auto-validate.md uses `rejectTargetFile` the same way. The reason is test/test-skf-chain-reachability.py: `_next_step()` pulls a single `nextStepFile` value per step file (first regex match) and walks that chain to assert every step is reachable, so a conditional jump must live under a different key — a second `nextStepFile` would be silently ignored or would replace the forward chain. Keep new branch pointers as `<reason>TargetFile` and leave `nextStepFile` as the linear successor.

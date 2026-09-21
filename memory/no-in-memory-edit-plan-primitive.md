---
created: "2026-03-18 21:00"
session: "d40284ec-234d-4a3e-bacb-2d72ebd53a47"
source: claude-mem
source_table: observations
source_ids: [1794, 1795, 5319, 5331]
---

# No in-memory edit-plan primitive in Claude Code

Claude Code's Edit/Write tools commit to disk on call; there is no held-in-memory buffer, staged edit or "edit plan" primitive, and `skill-check` needs files on disk. A step rule of the form "Do not write files — merge produces an edit plan for a later step" is therefore unenforceable fiction: skf-update-skill carried one and it was filed twice (issues #56 and #109) because the first fix only reworded it, leaving assistants to either write anyway or fabricate pseudo-plans that re-diffed themselves later. `src/skf-update-skill/references/merge.md` §6b now writes merged SKILL.md and stack reference files where they are produced, and `references/write.md` §1 only verifies the write from disk (HALT with `halted-for-manual-mismatch`, never repair) before writing derived artifacts (`metadata.json`, `provenance-map.json`, `evidence-report.md`, `context-snippet.md`). When authoring or reviewing any workflow step: write where the content is produced and verify afterwards; never defer a file write to a later step through an imagined in-context buffer — a real staging directory like create-skill's `_bmad-output/{skill-name}/` is the legitimate alternative.

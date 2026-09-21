---
created: "2026-05-16 05:07"
session: "ffc814aa-7ebd-4d13-a41d-9267584b3862"
source: claude-mem
source_table: observations
source_ids: [10062, 10063, 10067, 10068]
---

# skf-drop-skill deliberately has no resume-after-cancel; --dry-run is the preview path

Answering `[N]` at the skf-drop-skill §10 confirmation gate loses the selection (exit code 6, `halt_reason: "user-cancelled"`), and building a resume protocol for that was considered and rejected in issue #338 (lineage #331 → #335 → #338, closed 2026-05-16). Reasoning: resume of a destructive op replays a snapshot of a mutable manifest and filesystem (concurrent drops, skf-update-skill runs, manual edits) and would need re-validation anyway, saving only two prompts; the lineage showed zero user demand, and the original signal was a quality scanner run before `--dry-run` existed. What shipped instead is in `src/skf-drop-skill/references/select.md`: `--dry-run` (lines 292-305) prints a copy-pasteable `[DRY RUN]` selection line (skill, version, mode) so the choice survives in shell history, and the cancel message (line 312) points to `--dry-run`. Broader persistence was forwarded to the Workspace roadmap; do not reopen resume-after-cancel without new user demand, and expect quality scans to flag the lost selection state again.

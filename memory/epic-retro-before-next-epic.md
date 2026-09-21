---
created: "2026-05-27 00:11"
session: "229e49f1-aada-4d6f-b3d2-67e2c26cf711"
source: claude-mem
source_table: observations
source_ids: [13757, 13768, 13769]
---

# Epic retrospective runs before the next epic starts

When an epic's stories are all done, run the BMAD retrospective before creating the next epic's orchestration state document; the user set this: "we should run the retro before we jump into the next epic". The story-automator skill (installed at `.claude/skills/bmad-story-automator`) spawns a dedicated tmux retro session that writes `_bmad-output/implementation-artifacts/epic-N-retro-<date>.md` (gitignored) and may directly fix doc-rot in `docs/`; the Epic 3 retro rewrote `docs/verifying-a-skill.md` and `docs/workflows.md`, committed as `5ecb7a9a docs: fix doc-rot in workflow and verification docs`. Commit those doc fixes before the next epic's stories start so they build on accurate docs. Epics 1-4 (v2.0) each have a retro file under `_bmad-output/implementation-artifacts/`, which is local-only.

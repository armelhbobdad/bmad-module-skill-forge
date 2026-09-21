---
created: "2026-05-26 22:08"
session: "229e49f1-aada-4d6f-b3d2-67e2c26cf711"
source: claude-mem
source_table: observations
source_ids: [13670]
---

# Story-automator create session hang after artifact written

A story-automator create-phase tmux session (`sa-bmadmodu-…-create`) can stay busy 10+ minutes after the story file under `_bmad-output/implementation-artifacts/` is fully written, because `monitor-session` (`.claude/skills/bmad-story-automator/src/story_automator/commands/tmux.py`) only runs the artifact verifier once the session state is `completed` — a still-busy session just keeps polling. `orchestrator-helper verify-step create <story> --state-file <state>` checks the story artifact on disk independently of session state; once it returns `verified: true`, kill the session with `tmux-wrapper kill` and advance the epic run. The on-disk artifact check is the real completion signal, not the session going idle.

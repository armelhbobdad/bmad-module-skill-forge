---
created: "2026-05-27 01:34"
session: "af296e8c-2857-4198-9a59-278ef5201144"
source: claude-mem
source_table: observations
source_ids: [13800, 13801]
---

# Story-automator output file vanishing before parse

In the locally installed `.claude/skills/bmad-story-automator`, the dev step in `steps-c/step-03-execute.md` runs `monitor-session`, then `tmux-wrapper kill "$session"`, then `orchestrator-helper parse-output <output_file> dev` — but `tmux_kill_session()` in `src/story_automator/core/tmux_runtime.py` calls `cleanup_runtime_artifacts()`, which unlinks the very `/tmp/sa-<hash>-output-<session>.txt` that monitor-session just reported with `output_verified=true`. parse-output then fails with `{"status":"error","reason":"output file not found or empty"}` even though the story completed (seen 7 seconds apart during epic 4). Do not re-run the story: verify the step with `orchestrator-helper verify-step dev <story> --state-file <state>` (returns `verified=true`, `source="session_exit"`) and confirm the story status in `sprint-status.yaml`, then advance the state file.

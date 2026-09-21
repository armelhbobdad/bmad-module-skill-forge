---
created: "2026-05-27 00:05"
session: "229e49f1-aada-4d6f-b3d2-67e2c26cf711"
source: claude-mem
source_table: session_summaries
source_ids: [3409, 3410]
---

# Orphaned claude processes after story-automator tmux kill

`story-automator tmux-wrapper kill <session>` (the locally installed, gitignored `.claude/skills/bmad-story-automator`) only runs `tmux kill-session -t <session>` and deletes the `/tmp/sa-*` artifacts (`src/story_automator/core/tmux_runtime.py`, `tmux_kill_session`); the runner script starts the agent with `run_payload &` and nothing sends the child `claude` process a signal. During an epic run in this repo one such orphan kept running unattended for over four hours of CPU after its session was killed. After an orchestration ends (or after any manual `tmux kill-session`), run `pgrep -af claude` and kill the leftovers explicitly before starting the next epic.

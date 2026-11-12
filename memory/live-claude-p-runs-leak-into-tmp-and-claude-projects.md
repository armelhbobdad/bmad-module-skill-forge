---
created: "2026-09-28 10:32"
session: "2a5732e7-8d5b-4ace-85ad-06a1696c32ec"
---

# Live claude -p verification runs leak into /tmp and ~/.claude/projects

Live `claude -p` verification of SKF workflows in scratch projects (installer layout, `--permission-mode bypassPermissions`, `TMPDIR` set inside the project) still leaves the model's own scratch files in `/tmp` and `/tmp/claude-1000/`, ignoring `TMPDIR`, although no SKF step file names `/tmp`. The #510-#515 runs left about 30, among them `/tmp/skf-manifest-backup-*.json`, `/tmp/skf-cap.json`, `/tmp/skf-detect-acme/` and `/tmp/claude-1000/sc.json`. Each run also creates a session folder under `~/.claude/projects/` named after the scratch path (`-tmp-claude-1000-…-scratchpad-live-*`), and `--no-session-persistence` does not stop it: the 6.0.0 Test Skill validation runs on 2026-11-05 still left `…-scratchpad-oms-validate/<session>/` holding `subagents/agent-*.meta.json` and `tool-results/`. The maintainer's rule is that nothing stays under `/tmp` and the host environment is not changed, so pass `--no-session-persistence` anyway (keep a session only when a later `--resume` needs it) and note the start time before the runs. Afterwards delete only the `/tmp` and `/tmp/claude-1000/` top-level entries newer than that marker that the run transcripts name, and only the `~/.claude/projects/` folders named after the scratch path: the user's own sessions, tools (ast-grep MCP servers, uv locks) and other projects' folders sit beside them.

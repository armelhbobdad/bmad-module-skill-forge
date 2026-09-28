---
created: "2026-09-28 10:32"
session: "2a5732e7-8d5b-4ace-85ad-06a1696c32ec"
---

# Live claude -p verification runs leak into /tmp and ~/.claude/projects

When SKF workflows are verified live with `claude -p` inside scratch projects (installer layout, `--permission-mode bypassPermissions`, `TMPDIR` set to a folder inside the project), the model running the workflow still writes its own scratch files straight to `/tmp` and `/tmp/claude-1000/`, ignoring `TMPDIR`: the #510-#515 runs left `/tmp/skf-manifest-backup-*.json` (rename §6 backing up the manifest instead of holding its text), `/tmp/skf-cap.json`, `/tmp/skf-detect-acme/`, `/tmp/skf_lv511/` and `/tmp/claude-1000/sc.json`, among about 30 others, although no SKF step file names `/tmp`. Every `claude -p` run whose working folder is a scratch project also creates a session folder under `~/.claude/projects/` (`-tmp-claude-1000-…-scratchpad-live-*`, 26 of them in that session) unless `--no-session-persistence` is passed. The maintainer's rule for these runs is that nothing is left under `/tmp` and the host environment is not changed, so pass `--no-session-persistence` by default (keep a session only when a later `--resume` is needed, then delete its folder), note the start time before the runs, and afterwards delete only the `/tmp` and `/tmp/claude-1000/` top-level entries newer than that marker that the run transcripts name — the user's own sessions and tools (ast-grep MCP servers, uv locks they hold) share that folder.

---
created: "2026-03-26 09:01"
session: "9529ee88-4f65-4447-9f57-cf55852d5422"
source: claude-mem
source_table: observations
source_ids: [2492]
---

# Mode branch that skips a section must still set downstream state

In `skf-create-stack-skill`, `references/rank-and-confirm.md` has a `compose_mode` branch that skips import counting and ranking and goes straight to the menu. The original branch never set `confirmed_dependencies` (only the code-mode "Process User Response" section wrote it), so `detect-integrations.md`, `parallel-extract.md` and every later step iterated an empty list. The fix is the explicit `Set confirmed_dependencies = all raw_dependencies` line at the top of the compose branch (rank-and-confirm.md line 26). When adding a mode branch (compose, headless, stack, reference-app) that bypasses part of a step, grep the later steps for every workflow-state variable the skipped section writes and set each one inside the branch — these prose workflows have no compiler to flag an unset variable, and the failure only shows up several steps later.

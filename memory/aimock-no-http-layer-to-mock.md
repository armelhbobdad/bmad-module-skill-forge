---
created: "2026-04-09 23:28"
session: "3f373a49-0cdd-4599-b4f8-6b8214af3f47"
source: claude-mem
source_table: observations
source_ids: [5152, 5156, 5157]
---

# AIMock cannot automate SKF workflow tests

CopilotKit's AIMock (an HTTP mock server for LLM APIs with VCR-style record/replay) was evaluated in April 2026 as a way to automate the manual workflow test scenarios and rejected. SKF workflows are instruction files executed inside the IDE agent (Claude Code, Cursor), and neither the installer under `tools/cli/` nor the Python helpers in `src/shared/scripts/` make any LLM HTTP call, so there is nothing at the HTTP layer to intercept. A record/replay PoC (`test/aimock/`, `test:aimock:record` needing `ANTHROPIC_API_KEY`) was built but never merged: `git log -S'aimock'` on main is empty and `package.json` has no such script. At best an LLM mock validates a single-step "LLM emits JSON → Python script consumes it" contract (for example the skf-test-skill score stage, `references/score.md` feeding `compute-score.py`), never a multi-turn workflow, tool use or file I/O; `npm test` remains custom Node scripts plus `uv run pytest` over the shared scripts, and workflow behaviour is still verified by running the workflow in an IDE.

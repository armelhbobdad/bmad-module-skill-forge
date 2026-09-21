---
created: "2026-05-15 15:41"
session: "77c2e3d9-3742-4582-9b5e-94101963b3ee"
source: claude-mem
source_table: session_summaries
source_ids: [2767, 2768, 2769]
---

# Nested subagent orchestration flattens in quality analysis

Running the bmad-workflow-builder Analyze pass (`.claude/skills/bmad-workflow-builder/references/scan-orchestration.md`: deterministic prepass scripts plus five lenses "as parallel subagents", output under `{skill}/.analysis/<timestamp>/`) over every `src/skf-*` skill by spawning one orchestrator subagent per skill failed for 7 of 13 skills. A subagent cannot spawn subagents, so each orchestrator executed the lens instructions inline, returned only an architecture scan, and produced no synthesis, grade or report HTML. Run the analysis from the top-level session one skill at a time so the parent spawns the lenses itself, or make the spawn directive explicit and confirm every lens returned before synthesis. The prepass JSON survives under `.analysis/` (gitignored via `**/.analysis` in .gitignore) and can be reused on a retry instead of re-running the scripts.

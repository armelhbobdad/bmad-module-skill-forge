---
created: "2026-04-09 01:19"
session: "59c7313e-e858-4b50-adc3-7e7cd9e3d750"
source: claude-mem
source_table: observations
source_ids: [4943]
---

# Pipeline alias recognition lives in three runtime files, not in docs

In April 2026 the `forge-quick` alias was documented in `docs/workflows.md`, `docs/agents.md`, `src/shared/references/pipeline-contracts.md` and `src/knowledge/skill-lifecycle.md` but missing from the forger's own instruction file, so the agent could not expand `forge-quick` into `QS TS EX` at runtime. Today an alias must exist in all three runtime locations: the recognition list in `src/skf-forger/SKILL.md` (Pipeline Mode paragraph, "Only the alias names need recognizing here"), the `ALIASES` table in `src/skf-forger/scripts/parse-pipeline.py` (the deterministic expander, covered by `test/test-skf-parse-pipeline.py::test_all_aliases_expand`), and the alias table in `src/shared/references/pipeline-contracts.md` (the prose fallback when the script cannot run). `docs/` and `src/knowledge/` pages are informational only and nothing tests that the copies agree, so an alias added or renamed in docs alone silently does nothing.

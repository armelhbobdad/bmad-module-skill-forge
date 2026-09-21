---
created: "2026-04-09 22:52"
session: "3f373a49-0cdd-4599-b4f8-6b8214af3f47"
source: claude-mem
source_table: session_summaries
source_ids: [3437, 3438, 3475, 3476, 3481, 1534, 1533, 1542]
---

# Step-file bugs are invisible to the test suite

`npm test` runs ~2600 pytest functions over the 55 `src/shared/scripts/skf-*.py` helpers, but the LLM-followed step files under `src/skf-*/references/` only get structural checks: `test/test-skf-chain-reachability.py` (Stages-table paths exist, `nextStepFile` chain reachable) and the skf-campaign linter `test/test-skf-campaign-stepfiles.py`, whose docstring records that both HIGH-severity Epic 4 findings lived in step files and were found by adversarial review, not tests. Commit 7c3cc2b5 (2026-06-02) is another instance: three campaign helpers were invoked as `uv run python <script>` and would have failed with `ModuleNotFoundError` at runtime, latent because "the workflow has no end-to-end coverage yet"; the Stages-table/GATE drift in skf-analyze-source is a third. A green suite therefore does not validate a step-file change: after editing step prose, run the workflow live against a real repository (`@Ferris forge-auto <repo>` for the pipeline, or the single skill) or at least do an adversarial read of the changed step before calling it done.

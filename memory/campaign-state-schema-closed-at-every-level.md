---
created: "2026-05-27 03:39"
session: "52f47973-a120-4ff7-8232-2f3aa70f7aa9"
source: claude-mem
source_table: observations
source_ids: [13939, 13949, 14052, 14057]
---

# Campaign state schema closed at every level

`src/skf-campaign/assets/campaign-state-schema.json` sets `additionalProperties: false` at every level — root, `campaign`, `quality_gate`, `skills[]`, `dependency_graph`, and the nested `capstone` / `verification` / `refinement` objects — and every campaign step runs `uv run scripts/campaign-validate-state.py --state-file ...` on entry, HALTing with exit 3 `invalid-state` on failure. So a new key a step writes into `_campaign-state.yaml` succeeds in the writing step and fails at the next step's load with `Additional properties are not allowed ('<key>' was unexpected)` and `halt_reason: state-invalid`. Extend the schema first and add the matching `test_extra_*_property_rejected` / passes cases in `test/test-skf-campaign-state.py`; this blocked three consecutive changes (capstone quality, verify/refine results, report aggregation) until the schema gained `architecture_doc_path`, `capstone`, `verification` and `refinement`. The convention for a new derived result is a nullable summary object of counts plus a path to the artifact on disk, never the full result.

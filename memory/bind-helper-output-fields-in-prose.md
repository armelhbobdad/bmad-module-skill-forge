---
created: "2026-05-15 14:45"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9581, 9582, 9588, 9600]
---

# Every new helper output field must be bound in the consuming reference file

Adding a field to a shared helper's JSON output (`src/shared/scripts/*.py`) is only half the job: the reference `.md` that consumes it must add an explicit `{flag}` ← `field` line in its flag-binding section, or the LLM silently falls back to re-parsing the source file or to null. This was hit in skf-setup: after commit 04996fab moved forge-tier.yaml reading into `skf-detect-tools.py --prior-state-from`, `detect-and-tier.md` §3 did not bind the four returned `prior.previous_ccc_*` fields, so `ccc-index.md` either re-parsed the YAML the refactor meant to retire or defaulted to null and forced a full ccc re-index on every run. The fix binds all `prior.*` and `deltas.*` fields in `src/skf-setup/references/detect-and-tier.md`, and `report.md` branches on the `{tier_changed}` boolean with a `{previous_tier}` null guard instead of doing set arithmetic in prose. No test executes prompt files, so this class of gap is only found by reading the consumer; when you extend a helper's output, grep every `<name>ProbeOrder` consumer and add the binding in the same change.

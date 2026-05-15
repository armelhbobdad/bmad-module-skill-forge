---
# `{nextStepFile}` is resolved by probing both candidate roots in order.
# HALT if neither exists — step 6 §7 should have caught this already, but
# this step re-asserts the invariant at dispatch time.
nextStepFileProbeOrder:
  - '{project-root}/_bmad/skf/shared/health-check.md'
  - '{project-root}/src/shared/health-check.md'
---

# Step 7: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check. This is the terminal step of test-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 6
- Delegate directly to the resolved health-check path with no additional commentary
- Do not attempt any other action between loading this step and executing the resolved file

## MANDATORY SEQUENCE

1. Probe `{nextStepFileProbeOrder}` in order. Use the FIRST path that exists as `{nextStepFile}`. HALT with the diagnostic from step 6 §7 if neither exists.
2. Load `{nextStepFile}`, read it fully, then execute it.

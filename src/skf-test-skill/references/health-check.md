---
# `{nextStepFile}` is resolved by probing both candidate roots in order.
# HALT if neither exists — step 6 §7 should have caught this already, but
# this step re-asserts the invariant at dispatch time.
nextStepFileProbeOrder:
  - '{project-root}/_bmad/skf/shared/health-check.md'
  - '{project-root}/src/shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

Probe `{nextStepFileProbeOrder}` in order; load and execute the first path that exists as `{nextStepFile}`, else HALT with a diagnostic naming both candidate paths. This is the terminal step of test-skill.

---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

# Step 7: Workflow Health Check

Communicate with the user in `{communication_language}`.

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of quick-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step-06
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then proceed to execute it.

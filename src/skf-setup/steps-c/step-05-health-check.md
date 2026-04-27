---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. This is a delegation-only step (no user-visible output of its own); shared/health-check.md inherits the language directive on load. -->

# Step 5: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of setup — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step-04
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then execute it.

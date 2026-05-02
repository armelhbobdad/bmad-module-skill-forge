---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/`
# during development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

# Step 6: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of brief-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step-05
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then execute it.

## CRITICAL STEP COMPLETION NOTE

Step 06 is the terminal stage of brief-skill. After `{nextStepFile}` returns control, the brief-skill workflow is fully complete — do not re-enter step-05 or step-06, do not load any further step file, and do not loop back into the workflow.

---
# `shared/health-check.md` resolves relative to the SKF module root
# (`_bmad/skf/` when installed, `src/` during development), NOT relative
# to this step file.
nextStepFile: 'shared/health-check.md'
---

# Step 9: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of create-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 8
- Delegate directly to `{nextStepFile}` with no additional commentary
- In batch mode, this step is only reached after the final brief — step 8 loops back to load-brief for remaining briefs and skips chaining here
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then execute it.

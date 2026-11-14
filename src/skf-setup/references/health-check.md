---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. This is a delegation-only step (no user-visible output of its own); shared/health-check.md inherits the language directive on load. -->

# Step 5: Workflow Health Check

## STEP GOAL:

Hand off to the shared health check at `{nextStepFile}`; setup is done when it returns.

## Rules

- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then execute it.

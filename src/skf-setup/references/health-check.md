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

- `{quiet_mode}` reaches `{nextStepFile}` as activation set it: skf-setup is the only workflow that sets it, and when it is true the shared health check displays nothing of its own, queues any findings locally, and displays step 4's `{setup_envelope_line}` verbatim last, as the final message of a standalone run; when `{pipeline_mode}` is true, control then returns to the forger, which keeps chaining
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief

## MANDATORY SEQUENCE

Load `{nextStepFile}`, read it fully, then execute it.

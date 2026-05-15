---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of verify-stack — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 6
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

Attempt to load `{nextStepFile}`.

- **If `{nextStepFile}` loads successfully:** Read it fully, then execute it.
- **If `{nextStepFile}` cannot be resolved or loaded** (e.g., running against a partial installation, module root not resolvable, or the file has been removed): log exactly `health-check unavailable at {path}` (substitute the attempted resolved path) to the user-visible output and exit the workflow cleanly. Do NOT HALT with an error — the health check is an optional self-improvement hook, and the feasibility report (written in step 6) is the authoritative workflow output. Exit cleanly so CI and headless runs do not fail on a missing optional hook.

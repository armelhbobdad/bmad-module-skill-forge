---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of rename-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 3
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}`

## MANDATORY SEQUENCE

1. **Release the rename lock.** Delete `{forge_data_folder}/{old_name}/.skf-rename.lock` if it still exists (the lock is acquired in select.md §4b and released here as the terminal cleanup). A no-op when `old_name` was never resolved or the lock was already removed by an earlier halt path.

   ```bash
   rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"
   ```

2. Load `{nextStepFile}`, read it fully, then execute it.

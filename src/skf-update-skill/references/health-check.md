---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of update-skill — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 7
- Delegate directly to `{nextStepFile}` with no additional commentary
- Do not attempt any other action between loading this step and executing `{nextStepFile}` (other than the lock release below)

## MANDATORY SEQUENCE

1. **Release the concurrency lock** acquired by init.md §1b (skip when `detect_only_mode` or `dry_run_mode` is true — those modes never acquired one):

   ```bash
   rm -f "{forge_data_folder}/{skill_name}/.skf-update.lock"
   ```

   The lock release MUST run before delegating to the shared health-check, since the health-check is the terminal step — once it returns, the workflow is done and any held lock becomes orphaned for the next run to clean up. Releasing here keeps the lock lifecycle tight against the workflow's actual span.

2. Load `{nextStepFile}`, read it fully, then execute it.

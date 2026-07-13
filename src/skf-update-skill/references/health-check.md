---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of update-skill — after the shared health check completes, the workflow is fully done. This step only releases the concurrency lock and delegates: no user-facing reports, file writes, or result contracts here (those belong in step 7).

## Steps

1. **Release the concurrency lock** acquired by init.md §1b (skip when `detect_only_mode` or `dry_run_mode` is true — those modes never acquired one):

   ```bash
   rm -f "{forge_data_folder}/{skill_name}/.skf-update.lock"
   ```

   Release the lock before delegating to the shared health-check: the health-check is the terminal step, so once it returns the workflow is done and any still-held lock is orphaned until the next run clears it. Releasing here keeps the lock lifecycle tight against the workflow's actual span.

2. Load `{nextStepFile}`, read it fully, then execute it.

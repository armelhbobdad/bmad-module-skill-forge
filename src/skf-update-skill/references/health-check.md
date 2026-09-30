---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
# Resolve `{sourceTreeHelper}` to the first existing path. Step 1b removes
# the private source tree init.md §6b prepared. If neither path exists,
# skip the call and continue: a later run removes a tree left behind once
# it is seven days old.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# Resolve `{runLockHelper}` to the first existing path. If neither exists,
# say the lock stays and continue: a later update replaces it once stale.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of update-skill: after the shared health check completes, the workflow is fully done. This step only releases the concurrency lock and the private source tree and removes this update's run folder, then delegates: no user-facing reports, file writes, or result contracts here (those belong in step 7), apart from one line when the lock or the tree stays on disk, or the folder does.

## Steps

1. **Release the concurrency lock** init.md §1b took (skip when `detect_only_mode` or `dry_run_mode` is true: those modes take none). Resolve `{runLockHelper}` ← first existing path in `{runLockProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {runLockHelper} release \
       --lock "{forge_data_folder}/{skill_name}/.skf-update.lock" \
       --owner "{lock_owner}"
   ```

   Never stop on the result:

   - `released` true, or `reason` `absent`: continue.
   - `reason` `not-owner`: another update took the lock over after this run's lock went stale, and the helper left that run's lock in place. Tell the user in one line "The run lock {forge_data_folder}/{skill_name}/.skf-update.lock now belongs to {held_by}: another update of {skill_name} took it over while this one ran.", then continue.
   - No candidate resolves, or the command fails or prints no JSON: tell the user in one line "The run lock {forge_data_folder}/{skill_name}/.skf-update.lock was not released ({the first stderr line, or 'skf-run-lock.py is missing'}); delete it when no update of {skill_name} is running.", then continue.

1b. **Remove the private source tree** init.md §6b prepared, in every mode (`--detect-only` and `--dry-run` included), when `{source_tree}` is set: resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} close --tree "{source_tree}"`. `{source_tree}` is the `tree` path the helper's `open` printed in init.md §6b; close also takes the run folder that holds it (where `changed-files.json` sits), and refuses any other folder. Bind `{source_tree_close}` ← `status` and `{source_tree_close_warnings}` ← `warnings`, and never stop on the result:

   - `removed` or `missing`: continue.
   - `refused`: run the command once more with `--tree` set to the exact `tree` value `open` printed, and bind its result the same way.
   - `left`, `refused` again, or the command fails or prints no JSON: tell the user in one line "The private source tree {source_tree} was not removed ({source_tree_close}, {source_tree_close_warnings}); a later update removes it once it is seven days old.", then continue.

1c. **Remove this update's run folder** `{run_dir}`, which step 2 created, in every mode (`--detect-only` and `--dry-run` included), when `{run_dir}` is bound: from `{project-root}`, run `rm -rf "{run_dir}"`. It holds only the helper files steps 2 and 3 passed between them. When it fails, tell the user in one line "The run folder {run_dir} was not removed; delete it.", then continue.

2. Load `{nextStepFile}`, read it fully, then execute it.

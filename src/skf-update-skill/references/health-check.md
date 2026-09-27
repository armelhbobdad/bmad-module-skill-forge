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
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of update-skill — after the shared health check completes, the workflow is fully done. This step only releases the concurrency lock and the private source tree, then delegates: no user-facing reports, file writes, or result contracts here (those belong in step 7), apart from one line when the tree stays on disk.

## Steps

1. **Release the concurrency lock** acquired by init.md §1b (skip when `detect_only_mode` or `dry_run_mode` is true — those modes never acquired one):

   ```bash
   rm -f "{forge_data_folder}/{skill_name}/.skf-update.lock"
   ```

   Release the lock before delegating to the shared health-check: the health-check is the terminal step, so once it returns the workflow is done and any still-held lock is orphaned until the next run clears it. Releasing here keeps the lock lifecycle tight against the workflow's actual span.

1b. **Remove the private source tree** init.md §6b prepared, in every mode (`--detect-only` and `--dry-run` included), when `{source_tree}` is set: resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} close --tree "{source_tree}"`. `{source_tree}` is the `tree` path the helper's `open` printed in init.md §6b; close also takes the run folder that holds it (where `changed-files.json` sits), and refuses any other folder. Bind `{source_tree_close}` ← `status` and `{source_tree_close_warnings}` ← `warnings`, and never stop on the result:

   - `removed` or `missing`: continue.
   - `refused`: run the command once more with `--tree` set to the exact `tree` value `open` printed, and bind its result the same way.
   - `left`, `refused` again, or the command fails or prints no JSON: tell the user in one line "The private source tree {source_tree} was not removed ({source_tree_close}, {source_tree_close_warnings}); a later update removes it once it is seven days old.", then continue.

2. Load `{nextStepFile}`, read it fully, then execute it.

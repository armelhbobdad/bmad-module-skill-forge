---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
nextStepOptions:
  step 2: 'scan-project.md'
  step 3: 'identify-units.md'
  step 4: 'map-and-detect.md'
  step 5: 'recommend.md'
  step 6: 'generate-briefs.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Continue Analysis

## STEP GOAL:

To resume an unfinished analyze-source run from where a previous session left off, by reading the analysis report's progress state and routing to the correct next step. Init section 1 sends only an unfinished report of the step-by-step analysis here: it archives a finished report and one whose `mode` is `'auto'` and starts a fresh analysis instead.

## MANDATORY SEQUENCE

### 2. Read Progress State

Read {outputFile}'s frontmatter `stepsCompleted` and `run_dir`: `{earlier_run_dir}` ← `run_dir`, empty when the report has none (one an older SKF wrote has none). It is the run folder of the session before this one when this exits 0:

```bash
case "{earlier_run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-analyze-source-"*/*) false ;; "{project-root}/_bmad-output/.skf-run/skf-analyze-source-"?*) [ -d "{earlier_run_dir}" ] ;; *) false ;; esac
```

A `run_dir` that holds a double quote, a backtick or a `$` names no run folder: skip the check and go on as when it exits non-zero.

- **It exits 0:** take that folder over. Append this session's sink files to it and delete this session's folder (`{run_dir}`, made at SKILL.md On Activation), then bind `{run_dir}` ← `{earlier_run_dir}`, so the result keeps the decisions and warnings recorded before this session, and the step that ends the run deletes the one folder:

  ```bash
  for f in headless-decisions.jsonl warnings.jsonl resolver-warning.txt; do if [ -f "{run_dir}/$f" ]; then cat "{run_dir}/$f" >> "{earlier_run_dir}/$f"; fi; done; rm -rf "{run_dir}"
  ```

- **It exits non-zero** (the folder is gone, or the value names no run folder of this workflow): keep this session's `{run_dir}` and delete nothing. Run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'resumed-without-run-folder: <the run_dir the report names, or none>: the decisions and warnings recorded before this session are not in this result'`, a single quote in it written as a backtick (if it fails, go on).

### 4. Determine Next Step

Map the last completed step to the next step file:

| Last Completed | Next Step |
|----------------|-----------|
| init | scan-project |
| scan-project | identify-units |
| identify-units | map-and-detect |
| map-and-detect | recommend |
| recommend | generate-briefs |

### 5. Update and Route

Update {outputFile} frontmatter:
```yaml
lastContinued: '{current_date}'
run_dir: '{run_dir}'
```

"**Resuming from {next_step_name}** (last completed: {the last entry of `stepsCompleted`})."

Then load, read the entire file, and execute the next step from {nextStepOptions}.

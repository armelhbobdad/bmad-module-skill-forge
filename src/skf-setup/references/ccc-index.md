---
nextStepFile: 'write-config.md'
# `{mergeCccExclusionsHelper}` = first existing path in
# `{mergeCccExclusionsProbeOrder}`; halt if neither exists.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`,
# for the blocked envelope a halt in this step emits under headless or quiet.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. User-visible status messages (indexing progress message) render in the user's language. -->

# Step 1b: CCC Index

## STEP GOAL:

When ccc is available, run `{mergeCccExclusionsHelper}` once: it prepares `.cocoindex_code/settings.yml` (running `ccc init` when needed), keeps its SKF exclusion patterns current, builds or refreshes the project index when it needs it, and writes its result to `{run_dir}/ccc-exclusions.json`, where step 2 and step 4 read it.

## Rules

- The script owns `ccc init`, every `settings.yml` edit, the index decision, `ccc index` and `ccc status`: run none of them yourself, and bind nothing from its output (steps 2 and 4 read the result file)
- Do not fail the workflow if settings preparation or ccc indexing fails: the result file records the failure, and the report shows it
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If no path in `mergeCccExclusionsProbeOrder` exists when section 2 runs (an install fault, not a settings failure), halt with phase `step 1b:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-merge-ccc-exclusions.py was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, pipe `{phase, reason, path}` to `uv run {emitEnvelopeHelper} emit-blocked` and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason

## MANDATORY SEQUENCE

### 1. Check Eligibility

If `{ccc}` (from step 1) is false, go to section 3 with no output. Otherwise continue to section 2, with or without `--ccc-skip-index`: the skip lane still prepares settings.yml, and only the index build is skipped.

### 2. Prepare the Settings and the Index

Unless `{quiet_mode}` is true, display: "**Preparing the ccc settings, then the semantic index if it needs building: a first index can take several minutes on large codebases (1000+ files). Run `ccc status` in another terminal to monitor progress.**"

Pass `{ccc_index_fresh}` (from step 1) and `{ccc_skip_index}` as `true` or `false`, and give the call an extended timeout (or run it in the background and wait for it to finish):

```bash
uv run {mergeCccExclusionsHelper} \
    --project-root "{project-root}" \
    --config "{project-root}/_bmad/skf/config.yaml" \
    --prior-state-from "{sidecar_path}/forge-tier.yaml" \
    --index-fresh "{ccc_index_fresh}" \
    --skip-index "{ccc_skip_index}" \
    --build-index \
    --result-to "{run_dir}/ccc-exclusions.json"
```

Go on to section 3 however the call ends: a non-zero exit, or a call the shell stopped, is no workflow error either (steps 2 and 4 report it as a failed index).

### 3. Auto-Proceed

Load `{nextStepFile}`, read it fully, and execute it.

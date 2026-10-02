---
nextStepFile: 'auto-index.md'
# `{forgeTierRwHelper}` = first existing path in `{forgeTierRwProbeOrder}`;
# halt if neither exists. The script owns the canonical forge-tier.yaml
# format and keeps the registries a rewrite must not lose.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`,
# for the blocked envelope a halt in this step emits under headless or quiet.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Halt-on-write-failure messages render in the user's language. -->

# Step 2: Write Configuration

## STEP GOAL:

Write the detected tools, the tier and the ccc index state to `{sidecar_path}/forge-tier.yaml` through `{forgeTierRwHelper}`, which reads them from the run folder and keeps the registries and the SKF exclusion record of an existing file, and make sure `{forge_data_folder}/` exists.

## Rules

- Never inline a YAML template for forge-tier.yaml: the script owns the canonical format
- Never create or edit `{sidecar_path}/preferences.yaml`: the installer writes it, and activation only reads it
- File write failures are errors: halt the workflow; under `{quiet_mode}` the blocked envelope is the only output, otherwise report the failure clearly
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If no path in `forgeTierRwProbeOrder` exists, halt with phase `step 2:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-forge-tier-rw.py was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, run `uv run {emitEnvelopeHelper} emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"`, which builds the payload itself (no `--path` for a halt without one, and `--stderr-from` where the halt names it), and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason

## MANDATORY SEQUENCE

### 1. Write forge-tier.yaml

```bash
uv run {forgeTierRwHelper} write-tools \
    --target "{sidecar_path}/forge-tier.yaml" \
    --detect-from "{run_dir}/detect-tools.json" \
    --ccc-from "{run_dir}/ccc-exclusions.json" 2> "{run_dir}/write-tools.err"
```

The script takes the tools and the tier from step 1's `detect-tools.json`, and the index state and the SKF exclusion record from step 1b's `ccc-exclusions.json`.

**If the script exits non-zero**: halt the workflow before chaining to step 3, with phase `step 2:write-tools`, path `{sidecar_path}/forge-tier.yaml` and as the reason the diagnostic in `{run_dir}/write-tools.err`. When `{quiet_mode}` is true, run the emitter, which reads that diagnostic itself, display its stdout line verbatim, and display nothing else: the envelope's `error` carries the path and reason. If the helper exits non-zero or prints no line, display the reason alone. Otherwise read that file and display the failure with its path and, as the reason, the `message` of its JSON error, else its first line.

```bash
uv run {emitEnvelopeHelper} emit-blocked --phase "step 2:write-tools" --path "{sidecar_path}/forge-tier.yaml" \
    --reason "<message>" --stderr-from "{run_dir}/write-tools.err"
```

### 2. Ensure the Forge Data Folder

```bash
mkdir -p "{forge_data_folder}" 2> "{run_dir}/forge-data-dir.err"
```

On non-zero exit, halt as section 1 does, with phase `step 2:forge-data-dir`, path `{forge_data_folder}` and the diagnostic in `{run_dir}/forge-data-dir.err` as the reason (an interactive run reads that file); under `{quiet_mode}`:

```bash
uv run {emitEnvelopeHelper} emit-blocked --phase "step 2:forge-data-dir" --path "{forge_data_folder}" \
    --reason "<message>" --stderr-from "{run_dir}/forge-data-dir.err"
```

### 3. Auto-Proceed

Once forge-tier.yaml is written, load `{nextStepFile}`, read it fully, and execute it.

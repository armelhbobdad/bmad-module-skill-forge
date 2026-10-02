---
nextStepFile: 'health-check.md'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`;
# halt if neither exists when section 4 emits the envelope. The script is the
# source of truth for the SKF_SETUP_RESULT_JSON contract: do not render the
# envelope from prose (LLM schema drift is the bug this script exists to
# prevent).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}; emit user-visible report text (FORGE STATUS banner, climb hint, REQUIRED TIER NOT MET block, breadcrumb) in {document_output_language}. The JSON envelope from section 4 is a machine contract — its keys and enum values stay English regardless. -->

# Step 4: Forge Status Report

## STEP GOAL:

Stage the run's report payload, display the FORGE STATUS banner that `{emitEnvelopeHelper}` renders from it (tier, tools, an upgrade for each tool below its minimum version, tier changes and tool-set deltas on re-runs, and a REQUIRED TIER NOT MET block on a required-tier miss), and (when headless or quiet) emit the schema-locked `SKF_SETUP_RESULT_JSON` envelope from the same payload.

## Rules

- Focus only on display + envelope emission
- The FORGE STATUS lines come from `render-report`: display them (translated when needed), and never compose, add or drop a line yourself
- Never inline-render the envelope JSON — the script owns the schema; drift breaks pipelines
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing status report is not the terminal step
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line section 4 builds, which section 5 displays on a tier miss and the shared health check displays last otherwise
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If section 4 finds no existing path in `emitEnvelopeProbeOrder`, halt with phase `step 4:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-emit-result-envelope.py was not found. Reinstall SKF, then re-run /skf-setup.` With no envelope helper to call, display that reason alone as the run's one line (the SKILL.md halt contract)

## MANDATORY SEQUENCE

### 1. Stage the Report Payload

Sections 2 and 4 read the helper outputs the run folder holds (`detect-tools.json`, `ccc-exclusions.json`, `qmd-classify.json`, `qmd-remove.json` and `clean-stale.json`, each when its step ran the helper), take the run's paths from `--project-root`, `--sidecar-path` and `--forge-data-folder` (the folders On Activation bound from preflight), and read one payload file with what neither gives, staged here on every run through a quoted heredoc:

```bash
cat > "{run_dir}/report-context.json" <<'SKF_JSON'
{
  "orphan_auto_resolution": {orphan_auto_resolution_or_null},
  "customization_resolver_unavailable": {customization_resolver_unavailable},
  "error": null
}
SKF_JSON
```

Write `{orphan_auto_resolution}` as the JSON object step 3 set (`{"action": "...", "source": "..."}`), or `null` when step 3 set none. `{customization_resolver_unavailable}` is JSON `null` unless SKILL.md On Activation bound it to the resolver's one-line failure reason; it is then that reason as a JSON string, its `"` and `\` escaped, and the envelope warns that the `{project-root}/_bmad/custom/` overrides were not applied. `error` stays `null`: a halt that names a phase never reaches this step, because it displays its own blocked envelope.

### 2. Display Forge Status Report (skip when `{quiet_mode}` is true)

Render the banner from the payload and the run folder:

```bash
uv run {emitEnvelopeHelper} render-report --run-dir "{run_dir}" --project-root "{project-root}" \
    --sidecar-path "{sidecar_path}" --forge-data-folder "{forge_data_folder}" \
    --tier-rules "{skill-root}/references/tier-rules.md" < "{run_dir}/report-context.json"
```

Display its stdout as one code block, so its alignment holds, keeping every line in its order. When `{document_output_language}` is not English, translate the prose and keep paths, commands, flags, tool names and tier names as they are. If the script exits non-zero, or no path in `emitEnvelopeProbeOrder` exists, display one line instead, `FORGE STATUS could not be rendered: <message>`, where `<message>` is the `message` of its stderr JSON, or `skf-emit-result-envelope.py was not found`, and continue: the forge is configured either way.

### 3. Required-Tier Failure Block (skip when `{quiet_mode}` is true)

If section 2 displayed `FORGE STATUS could not be rendered` and `{require_tier_satisfied}` is `false`, display one line: `REQUIRED TIER NOT MET: --require-tier {require_tier}, detected {calculated_tier}, missing <tools>`, where `<tools>` is `{require_tier_failure_missing_tools}` joined with `, `, so the section 5 halt shows its cause. A banner that rendered already ends with the REQUIRED TIER NOT MET block: display nothing more.

### 4. Emit Headless JSON Envelope

When `{quiet_mode}` is `true`, run `{emitEnvelopeHelper}` on the payload section 1 staged; `--run-dir` makes it read the staged helper outputs too, and the three path options give it the run's paths. It emits the single prefixed line `SKF_SETUP_RESULT_JSON: {…}` on stdout. Bind `{setup_envelope_line}` ← that stdout line, and do not display it here. It is the only line a headless or quiet run displays, and in a standalone run it must be the run's final message: `claude -p` prints only the final message, and the health check still runs after this step. Section 5 displays it on a tier miss; otherwise the shared health check displays it when it stops (its §0). Either way it is displayed verbatim as its own line (no code fence, no preface, no commentary), with nothing of setup's after it. When `{pipeline_mode}` is true, control then returns to the forger, which keeps chaining.

```bash
uv run {emitEnvelopeHelper} emit --run-dir "{run_dir}" --project-root "{project-root}" \
    --sidecar-path "{sidecar_path}" --forge-data-folder "{forge_data_folder}" < "{run_dir}/report-context.json"
```

**If the script exits non-zero:** a value in the payload or in a staged helper output is malformed: set `{setup_envelope_line}` to the empty string. Display nothing and continue (a missing JSON envelope on a headless or quiet run is a degraded but non-fatal state: the pipeline observer sees no envelope and treats the run as not completed cleanly).

### 5. Chain to Health Check

After the forge status report and any failure block have been displayed (under headless or quiet, once `{setup_envelope_line}` is bound), delete the run folder:

```bash
rm -f "{run_dir}/detect-tools.json" "{run_dir}/detect-tools.err" "{run_dir}/ccc-exclusions.json" "{run_dir}/write-tools.err" "{run_dir}/forge-data-dir.err" "{run_dir}/qmd-classify.json" "{run_dir}/qmd-remove.json" "{run_dir}/clean-stale.json" "{run_dir}/report-context.json" && rmdir "{run_dir}"
```

Then:

- If `{require_tier_satisfied}` is `false`, halt the workflow here without chaining to step 5. When `{quiet_mode}` is true, display `{setup_envelope_line}` verbatim as the run's final message in a standalone run (nothing when it is empty); when `{pipeline_mode}` is true, control then returns to the forger, which reads the envelope's `tier_failure` status. This halt emits no blocked envelope: the `tier_failure` envelope is its one line. The tier miss is terminal; `{onCompleteCommand}` does not fire on a failed run.
- Otherwise the forge is fully configured. If `{onCompleteCommand}` (resolved from `workflow.on_complete` at activation) is non-empty, carry out that instruction now: this is the workflow's terminal skill-specific action (for example, notify an onboarding channel); when `{quiet_mode}` is true, display nothing about it. Then load `{nextStepFile}`, read it fully, and execute it; under headless or quiet, the shared health check it chains to ends setup's output with `{setup_envelope_line}`.

The health-check step is the true terminal step on success — do not stop after the report on a passing run even though it reads as final. Step 5 in turn delegates to `shared/health-check.md`; after that returns, the setup workflow is fully done.

---
nextStepFile: 'ccc-index.md'
# `{detectToolsHelper}` = first existing path in `{detectToolsProbeOrder}`;
# halt if neither exists.
detectToolsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-tools.py'
  - '{project-root}/src/shared/scripts/skf-detect-tools.py'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`,
# for the blocked envelope a halt in this step emits under headless or quiet.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. The first-run preamble below is user-visible — render it in the user's language. -->

# Step 1: Detect Tools and Determine Tier

## STEP GOAL:

Through `{detectToolsHelper}`, verify the four forge tools (ast-grep, gh, qmd, ccc), each at its minimum version, compare them with the previous run's configuration, and calculate the capability tier. Then, on an interactive run, tell the user what setup is about to write before step 1b or step 2 writes anything.

## Rules

- Focus only on tool detection and tier calculation: write nothing but this run's folder and the detector's output and stderr in it (step 2 writes the configuration)
- Never reimplement tool probes or the tier rules in prose: the script is authoritative
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If no path in `detectToolsProbeOrder` exists, halt with phase `step 1:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-detect-tools.py was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, run `uv run {emitEnvelopeHelper} emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"`, which builds the payload itself (no `--path` for a halt without one, and `--stderr-from` where the halt names it), and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason

## MANDATORY SEQUENCE

### 1. Run Detection Helper

Create this run's folder:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX"
```

Bind `{run_dir}` ← the path it prints. If the folder cannot be created, halt with phase `step 1:run-folder`, `path` `{project-root}/_bmad-output/.skf-run`, and reason `Setup cannot proceed: the run folder could not be created: <message>`, where `<message>` is the command's first stderr line. With no run folder to hold that stderr, a quiet run repeats the command with its stderr piped to the emitter, which fills `<message>`; a repeat that succeeds removes the folder it made, and its reason then ends `(no error message)`:

```bash
{ mkdir -p "{project-root}/_bmad-output/.skf-run" && rmdir "$(mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX")"; } 2>&1 >/dev/null | uv run {emitEnvelopeHelper} emit-blocked --phase "step 1:run-folder" --path "{project-root}/_bmad-output/.skf-run" --reason "Setup cannot proceed: the run folder could not be created: <message>" --stderr-from -
```

Then run the detector into the folder:

```bash
uv run {detectToolsHelper} --project-root "{project-root}" \
    --prior-state-from "{sidecar_path}/forge-tier.yaml" \
    [--tier-override="{tier_override}"] [--require-tier="{require_tier}"] \
    > "{run_dir}/detect-tools.json" 2> "{run_dir}/detect-tools.err" && cat "{run_dir}/detect-tools.json"
```

Pass `--tier-override` only when `{tier_override}` (bound at activation from `preferences.yaml`) is non-null, and `--require-tier` only when `{require_tier}` is non-null, with the value exactly as activation bound it, even when it names no tier: the script rejects such a value, and the halt below then names the valid tiers.

Output is one JSON document on stdout; `DETECT_OUTPUT_SCHEMA` in the helper's docstring documents it.

**If the script exits non-zero or prints no JSON:** halt before section 2 with phase `step 1:detect-tools`, `path` `{project-root}`, and reason `Setup cannot proceed: tool detection failed: <message>`, where `<message>` is the diagnostic in `{run_dir}/detect-tools.err`: an interactive run reads that file and shows the `message` of its JSON error, else its first line. Under `{quiet_mode}` the blocked envelope is the only line displayed, and the emitter reads `<message>` from that file:

```bash
uv run {emitEnvelopeHelper} emit-blocked --phase "step 1:detect-tools" --path "{project-root}" \
    --reason "Setup cannot proceed: tool detection failed: <message>" --stderr-from "{run_dir}/detect-tools.err"
```

### 2. Parse Output and Set Context Flags

Steps 2 and 4 read the staged `detect-tools.json` themselves. Bind only what the next steps branch on (field paths are relative to the script's top-level object):

- `{ccc}` ← `tools.ccc.available`
- `{calculated_tier}` ← `tier.calculated`, the tier downstream steps act on
- `{require_tier_satisfied}` ← `require_tier.satisfied` (`true | false | null`; null when `--require-tier` was not set) and `{require_tier_failure_missing_tools}` ← `require_tier.missing_tools` (a list)
- `{previous_tier}` ← `prior.previous_tier` and `{previous_detection_date}` ← `prior.previous_detection_date` (both null on a first run)
- `{ccc_index_fresh}` ← `prior.ccc_index_fresh` (boolean; step 1b forwards it as `--index-fresh`)

A tier tool below its minimum version binds `false` here, like a missing one: it counts toward no tier, and step 4 names it with its upgrade from the staged output.

### 3. Show the First-Run Preamble or the Re-run Notice (skip when `{quiet_mode}` is true)

Now that section 2 has bound `{previous_tier}` and `{previous_detection_date}`, and before step 1b or step 2 writes anything, display one of these:

**First-run preamble:** when `{previous_tier}` is null:

"**About to set up the forge.** Setup has probed the available tools (ast-grep, gh, qmd and ccc, plus git and uv), read-only, and keeps their result in the scratch folder `{run_dir}` until it finishes. It goes on now to:

- Write `{sidecar_path}/forge-tier.yaml` (capability tier + tool state)
- Create `{forge_data_folder}/` if missing
- When ccc is available: prepare `{project-root}/.cocoindex_code/settings.yml` (run `ccc init` if it is missing, which in a git checkout also adds `/.cocoindex_code/` to `.gitignore`; merge the SKF exclusion patterns and remove ones a previous folder config left behind), then create or refresh the project ccc index

**About tiers:** SKF picks one of four tiers (Quick / Forge / Forge+ / Deep) based on which tools are installed, each at its minimum version or newer. **All four are fully usable**: higher tiers add power, they don't fix gaps. If you're new and only have a base Python install, Quick tier is the right starting point and the report at the end will show you exactly which tools to install or upgrade if you want to climb later."

**Re-run notice:** when `{previous_tier}` is non-null:

"**Forge already set up here:** {previous_tier} tier, detected {previous_detection_date}. The tools were just re-probed, and setup now refreshes this project's config and ccc index. Next time, to refresh only the tier without paying the ccc re-index cost, run it with `--ccc-skip-index`."

When `{require_tier_satisfied}` is `false`, end the one you display with: "`--require-tier {require_tier}` is not met: this run writes the detected tier but builds no ccc index and runs no registry hygiene."

### 4. Auto-Proceed

Load `{nextStepFile}`, read it fully, and execute it.

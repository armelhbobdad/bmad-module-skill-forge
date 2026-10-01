---
nextStepFile: 'ccc-index.md'
# `{detectToolsHelper}` = first existing path in `{detectToolsProbeOrder}`;
# halt if neither exists. This script is the source of truth for tool
# detection and tier calculation — no prose-driven probes.
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

Verify availability of the four forge tools (ast-grep, gh, qmd, ccc) and hold each tool to its minimum version, read any existing configuration for re-run comparison, check for tier override, and calculate the capability tier, all via `{detectToolsHelper}` so the deterministic work is done once, by a tested script, never by the LLM. Then, on an interactive run, tell the user what setup is about to write before step 1b or step 2 writes anything.

## Rules

- Focus only on tool detection and tier calculation: write nothing but this run's folder and the detector output in it (step 2 writes the configuration)
- Never reimplement tool probes or the tier rules in prose — the script is authoritative
- Tool command failures are not errors — they indicate unavailability (the script swallows them)
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If no path in `detectToolsProbeOrder` exists, halt with phase `step 1:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-detect-tools.py was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, pipe `{phase, reason, path}` to `uv run {emitEnvelopeHelper} emit-blocked` and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason

## MANDATORY SEQUENCE

### 1. Read the Tier Override

Read `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml`: `{tier_override}` ← its `tier_override` value, or null when the file or the value is absent.

### 2. Run Detection Helper

Create this run's folder:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX"
```

Bind `{run_dir}` ← the path it prints. If the folder cannot be created, halt with phase `step 1:run-folder`, `path` `{project-root}/_bmad-output/.skf-run`, and reason `Setup cannot proceed: the run folder could not be created: <message>`, where `<message>` is the first stderr line with each `'` replaced by a backtick and each `\` by `/`.

Then run the detector into the folder:

```bash
uv run {detectToolsHelper} --project-root "{project-root}" \
    --prior-state-from "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" \
    [--tier-override="{tier_override}"] [--require-tier="{require_tier}"] \
    > "{run_dir}/detect-tools.json" && cat "{run_dir}/detect-tools.json"
```

Pass `--tier-override` only when `{tier_override}` is non-null, and `--require-tier` only when `{require_tier}` is non-null, with the value exactly as activation bound it, even when it names no tier: the script rejects such a value, and the halt below then names the valid tiers. (`--project-root` lets the script compute the CCC-index freshness verdict, `prior.ccc_index_fresh`, so step 1b works from a boolean instead of doing timestamp math.)

Output is one JSON document on stdout; `DETECT_OUTPUT_SCHEMA` in the helper's docstring documents it.

**If the script exits non-zero or prints no JSON:** halt before section 3 with phase `step 1:detect-tools`, `path` `{project-root}`, and reason `Setup cannot proceed: tool detection failed: <message>`. `<message>` is the `message` of the stderr JSON `{"status":"error","message":...}`, or the first stderr line when stderr holds no JSON, with each `'` replaced by a backtick and each `\` by `/`. Under `{quiet_mode}` the blocked envelope is the only line displayed.

### 3. Parse Output and Set Context Flags

From the JSON, set these context flags. Field paths are relative to the script's top-level object.

From `tools`:

- `{ast_grep}` ← `tools.ast_grep.available`
- `{gh_cli}` ← `tools.gh_cli.available`
- `{qmd}` ← `tools.qmd.available`
- `{ccc}` ← `tools.ccc.available`
- `{ccc_daemon}` ← `tools.ccc.daemon` (`"healthy" | "stopped" | "error" | null`)
- `{security_scan}` ← `tools.security_scan.available` (informational only — never affects tier)

A tier tool below its minimum version binds `false` here, like a missing one: it counts toward no tier, and step 4 names it with its upgrade from the staged output.

From `tier`:

- `{calculated_tier}` ← `tier.calculated` — the tier downstream steps act on

From `require_tier`:

- `{require_tier_satisfied}` ← `require_tier.satisfied` (`true | false | null`; null when `--require-tier` was not set)
- `{require_tier_failure_missing_tools}` ← `require_tier.missing_tools` (a list)

From `prior` (populated by `--prior-state-from`; all fields null/empty on first run):

- `{previous_tier}` ← `prior.previous_tier`
- `{previous_detection_date}` ← `prior.previous_detection_date`
- `{previous_ccc_last_indexed}` ← `prior.previous_ccc_last_indexed`
- `{previous_ccc_file_count}` ← `prior.previous_ccc_file_count` (integer or null; step 1b carries it forward on the fresh-index path so `forge-tier.yaml` keeps its `file_count` across re-runs that do not re-index)
- `{ccc_index_fresh}` ← `prior.ccc_index_fresh` (boolean; the script's deterministic freshness verdict — prior index covers this project AND status was fresh/created AND `last_indexed` is within the staleness threshold of now. Step 1b forwards it to its exclusion helper as `--index-fresh`, which folds it into the index decision, instead of doing timestamp math.)

### 4. Show the First-Run Preamble or the Re-run Notice (skip when `{quiet_mode}` is true)

Now that section 3 has bound `{previous_tier}` and `{previous_detection_date}`, and before step 1b or step 2 writes anything, display one of these:

**First-run preamble:** when `{previous_tier}` is null:

"**About to set up the forge.** Setup has probed the available tools (ast-grep, gh, qmd and ccc, plus git and uv), read-only, and keeps their result in the scratch folder `{run_dir}` until it finishes. This workflow will now:

- Write `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (capability tier + tool state)
- Write `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml` (first-run defaults)
- Create `{forge_data_folder}/` if missing
- When ccc is available: prepare `{project-root}/.cocoindex_code/settings.yml` (run `ccc init` if it is missing, which in a git checkout also adds `/.cocoindex_code/` to `.gitignore`; merge the SKF exclusion patterns and remove ones a previous folder config left behind), then create or refresh the project ccc index

**About tiers:** SKF picks one of four tiers (Quick / Forge / Forge+ / Deep) based on which tools are installed, each at its minimum version or newer. **All four are fully usable**: higher tiers add power, they don't fix gaps. If you're new and only have a base Python install, Quick tier is the right starting point and the report at the end will show you exactly which tools to install or upgrade if you want to climb later.

Press Esc or Ctrl+C now if this isn't the right project: none of the files above has been written yet (if you stop here, delete `{run_dir}`)."

**Re-run notice:** when `{previous_tier}` is non-null:

"**Forge already set up here:** {previous_tier} tier, detected {previous_detection_date}. The tools were just re-probed; going on refreshes config/index in this project. To refresh the tier without paying the ccc re-index cost, re-run with `--ccc-skip-index`. Press Esc or Ctrl+C now if this isn't the project you meant: nothing has been rewritten yet (if you stop here, delete `{run_dir}`)."

### 5. Auto-Proceed

After context flags are populated, unless `{quiet_mode}` is true, display "**Proceeding to CCC index check...**". Then load `{nextStepFile}`, read it fully, and execute it.

---
nextStepFile: 'auto-index.md'
# `{forgeTierRwHelper}` = first existing path in `{forgeTierRwProbeOrder}`;
# halt if neither exists. The script owns the canonical forge-tier.yaml format
# and the array-preservation contract that protects qmd_collections /
# ccc_index_registry / staleness_threshold_hours from being lost on rewrite.
# Do not fall back to inline YAML emission — a prose-rendered template drifts
# from the script and silently corrupts downstream skills.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# Resolve `{emitEnvelopeHelper}` for the headless/quiet blocked-envelope emit
# on write failures and a missing helper (the regular envelope assembly
# happens in step 4, but these halts never reach step 4 — see section 1's
# blocked-emit protocol).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Halt-on-write-failure messages render in the user's language. -->

# Step 2: Write Configuration

## STEP GOAL:

Write the detected tool availability and calculated tier to `forge-tier.yaml` (preserving registry arrays from any existing file), create `preferences.yaml` with first-run defaults if it does not exist, and ensure the `forge-data/` directory is present. All file mutations go through `{forgeTierRwHelper}` so the format is locked, atomic, and array-preservation is guaranteed.

## Rules

- Focus only on writing configuration files and creating directories
- Do not re-detect tools — use results from step 1
- Never inline a YAML template for forge-tier.yaml or preferences.yaml — the script owns the canonical format
- File write failures are errors: halt the workflow; under `{quiet_mode}` the blocked envelope is the only output, otherwise report the failure clearly
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If no path in `forgeTierRwProbeOrder` exists, halt with phase `step 2:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-forge-tier-rw.py was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, pipe `{phase, reason, path}` to `uv run {emitEnvelopeHelper} emit-blocked` and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason

## MANDATORY SEQUENCE

### 1. Write forge-tier.yaml

Build the JSON payload from context flags set by step 1 and step 1b. The payload must include `tools`, `tier`, and `ccc_index`; the script handles `tier_detected_at` defaulting to "now" if absent and preserves `qmd_collections`, `ccc_index_registry`, and a user-customized `ccc_index.staleness_threshold_hours` from any existing file, and keeps the existing `ccc_index.exclude_patterns` (the record of SKF-owned ccc exclusions) when `{ccc_exclude_patterns}` is `null`.

Invoke via `uv run`.

```bash
echo '{
  "tools": {
    "ast_grep": {ast_grep},
    "gh_cli": {gh_cli},
    "qmd": {qmd},
    "ccc": {ccc},
    "ccc_daemon": {ccc_daemon},
    "security_scan": {security_scan}
  },
  "tier": "{calculated_tier}",
  "ccc_index": {
    "indexed_path": {ccc_indexed_path},
    "last_indexed": {ccc_last_indexed},
    "status": "{ccc_index_result}",
    "file_count": {ccc_file_count},
    "exclude_patterns": {ccc_exclude_patterns}
  }
}' | uv run {forgeTierRwHelper} write-tools \
       --target "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml"
```

The script atomically writes the file via temp + fsync + rename (crash-safe) and returns a JSON response with `wrote`, `preserved_arrays.qmd_collections` count, `preserved_arrays.ccc_index_registry` count, and the resolved `tier`.

**If the script exits non-zero**: parse the stderr JSON `{"status":"error","message":...}` and halt the workflow before chaining to step 3, with phase `step 2:write-tools`, path `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` and the message as the reason. When `{quiet_mode}` is true, pipe that `{phase, reason, path}` payload, with each `'` in the reason replaced by a backtick and each `\` by `/`, to `uv run {emitEnvelopeHelper} emit-blocked`, display the helper's stdout line verbatim, and display nothing else: the envelope's `error` carries the path and reason (`{emitEnvelopeHelper}` resolves from this file's `emitEnvelopeProbeOrder`; the subcommand declares zero dependencies). If the helper exits non-zero or prints no line, display the reason alone. Otherwise display the failure with its path and reason.

### 2. Initialize preferences.yaml

```bash
uv run {forgeTierRwHelper} init-prefs \
    --target "{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml"
```

The script creates the file with first-run defaults (`tier_override: ~`, `passive_context: true`, `headless_mode: false`, `compact_greeting: false`, `tessl_review_workspace: ~`) if the file does not exist. When the file already exists, the script refuses to overwrite (preserves user customization) and reports `wrote: false`.

**Parse the response and set context flags for step 4:**

- `{preferences_yaml_created}` ← `wrote` (true on first run, false on re-run when the file pre-existed)

**If the script exits non-zero**: same halt-and-blocked-envelope-emit pattern as section 1, with `phase: "step 2:init-prefs"` and the matching path.

### 3. Ensure forge-data/ Directory

Run `mkdir -p {forge_data_folder}`. The `-p` flag is idempotent (creates parents, exits 0 if the directory already exists), so the prompt does no existence-check reasoning. On non-zero exit, halt with the same blocked-envelope-emit pattern as section 1, using `phase: "step 2:forge-data-dir"` and the matching path.

### 4. Auto-Proceed

After forge-tier.yaml has been written successfully and preferences.yaml exists (created or pre-existing), unless `{quiet_mode}` is true, display "**Proceeding to QMD collection hygiene...**". Then load `{nextStepFile}`, read it fully, and execute it.

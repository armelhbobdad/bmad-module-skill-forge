---
nextStepFile: './step-03-auto-index.md'
# Resolve `{forgeTierRwHelper}` by probing `{forgeTierRwProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — the script owns the canonical
# forge-tier.yaml format AND the array-preservation contract that protects
# qmd_collections / ccc_index_registry / staleness_threshold_hours from being
# lost on rewrite. NEVER fall back to inline YAML emission — drift between the
# script and a prose-rendered template will silently corrupt downstream skills.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
---

# Step 2: Write Configuration

## STEP GOAL:

Write the detected tool availability and calculated tier to `forge-tier.yaml` (preserving registry arrays from any existing file), create `preferences.yaml` with first-run defaults if it does not exist, and ensure the `forge-data/` directory is present. All file mutations go through `{forgeTierRwHelper}` so the format is locked, atomic, and array-preservation is guaranteed.

## Rules

- Focus only on writing configuration files and creating directories
- Do not re-detect tools — use results from step-01
- Never inline a YAML template for forge-tier.yaml or preferences.yaml — the script owns the canonical format
- File write failures are errors — report clearly and halt the workflow

## MANDATORY SEQUENCE

### 1. Write forge-tier.yaml

Build the JSON payload from context flags set by step-01 and step-01b. The payload must include `tools`, `tier`, and `ccc_index`; the script handles `tier_detected_at` defaulting to "now" if absent and preserves `qmd_collections`, `ccc_index_registry`, and a user-customized `ccc_index.staleness_threshold_hours` from any existing file.

Invoke via `uv run` so the script's PEP 723 PyYAML dependency resolves automatically (this is what `docs/getting-started.md`'s uv prereq exists for). Bare `python3` would fail on a fresh interpreter with `ModuleNotFoundError`.

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

The script atomically writes the file via temp + fsync + rename (mirrors `skf-atomic-write.py`'s crash-safety contract) and returns a JSON response with `wrote`, `preserved_arrays.qmd_collections` count, `preserved_arrays.ccc_index_registry` count, and the resolved `tier`.

**Parse the response and set context flags for step-04:**

- `{forge_tier_yaml_path}` ← `wrote`
- `{forge_tier_qmd_collections_count}` ← `preserved_arrays.qmd_collections`
- `{forge_tier_ccc_registry_count}` ← `preserved_arrays.ccc_index_registry`

**If the script exits non-zero**: parse the stderr JSON `{"status":"error","message":...}`, set `{error: {phase: "step-02:write-tools", path: "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml", reason: <message>}}` for step-04's envelope, and halt the workflow before chaining to step-03.

### 2. Initialize preferences.yaml

```bash
uv run {forgeTierRwHelper} init-prefs \
    --target "{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml"
```

The script creates the file with first-run defaults (matching the prior inline template — `tier_override: ~`, `passive_context: true`, `headless_mode: false`, `compact_greeting: false`, plus reserved-for-future-use commented fields) IF the file does not exist. When the file already exists, the script refuses to overwrite (preserves user customization) and reports `wrote: false`.

**Parse the response and set context flags for step-04:**

- `{preferences_yaml_created}` ← `wrote` (true on first run, false on re-run when the file pre-existed)

**If the script exits non-zero**: same halt-and-report pattern as section 1, with `phase: "step-02:init-prefs"` and the matching path.

### 3. Ensure forge-data/ Directory

Check if `{forge_data_folder}` directory exists:

- If missing: create it. Store `{forge_data_dir_created: true}` in context.
- If exists: skip silently. Store `{forge_data_dir_created: false}` in context.

If the create fails (parent unwritable, disk full, permission denied), set `{error: {phase: "step-02:forge-data-dir", path: "{forge_data_folder}", reason: <error message>}}` for step-04's envelope and halt the workflow.

### 4. Auto-Proceed

After forge-tier.yaml has been written successfully and preferences.yaml exists (created or pre-existing), display "**Proceeding to QMD collection hygiene...**", then load `{nextStepFile}`, read it fully, and execute it.

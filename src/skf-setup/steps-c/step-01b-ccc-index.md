---
nextStepFile: './step-02-write-config.md'
# Resolve `{mergeCccExclusionsHelper}` by probing `{mergeCccExclusionsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves — the script owns config-value
# validation and the set-union merge into .cocoindex_code/settings.yml; no
# fallback to prose-driven validation.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
---

# Step 1b: CCC Index Verification

## STEP GOAL:

If ccc is available (`{ccc: true}` from step-01), invoke `{mergeCccExclusionsHelper}` to validate config-driven SKF exclusion patterns and merge them into `.cocoindex_code/settings.yml`, then verify the project's ccc index exists and create or refresh it if needed. Store index state and exclusion-merge results in context for step-02 to write into forge-tier.yaml and for step-04 to surface in the JSON envelope.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## Rules

- Focus only on ccc index verification, exclusion-pattern merge, and (re-)indexing
- Do not display skip messages for Quick/Forge tiers
- Do not fail the workflow if ccc indexing fails
- Never reimplement the exclusion-pattern validation in prose — the script owns the PR #248 rules

## MANDATORY SEQUENCE

### 1. Check Eligibility

Read `{ccc}` from step-01 context.

**If `{ccc}` is false:** Set `{ccc_index_result: "none", ccc_indexed_path: null, ccc_last_indexed: null, ccc_exclude_patterns: [], ccc_exclusion_warnings: [], settings_yml_written: false, settings_yml_patterns_added: 0}`. Proceed directly to section 4 (Auto-Proceed) — no output, no messaging.

**If `{ccc}` is true:** Continue to section 2.

### 2. Check Existing Index State

Read existing forge-tier.yaml at `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (if it exists from a previous run).

Read `staleness_threshold_hours` from `ccc_index.staleness_threshold_hours` in the existing forge-tier.yaml (default: 24 if not present or not a number). Use this value for the freshness check below.

Check the `ccc_index` section:

- If `ccc_index.indexed_path` matches `{project-root}` AND `ccc_index.status` is `"fresh"` or `"created"`:
  - Check freshness: if `ccc_index.last_indexed` is within `staleness_threshold_hours` of now → index is fresh
  - Store `{ccc_index_result: "fresh", ccc_indexed_path: {project-root}, ccc_last_indexed: {existing timestamp}}`
  - Set `{needs_reindex: false}` — exclusions still get merged in section 3, which may force a re-index

- If `ccc_index.indexed_path` matches `{project-root}` but timestamp is older than threshold:
  - Set `{needs_reindex: true}`

- If `ccc_index` is missing, has null values, or path doesn't match:
  - Set `{needs_reindex: true}`

### 3. Merge SKF Exclusion Patterns

SKF infrastructure and output directories must be excluded from the CCC index — they contain workflow instructions, build artifacts, and generated skills that pollute semantic search results with zero extraction value.

Run the merge helper, forwarding the resolved config values from the workflow activation context. Invoke via `uv run` so PEP 723 inline metadata resolves the script's PyYAML dependency automatically (per `docs/getting-started.md`'s prereq list — uv exists for this exact purpose). Bare `python3` will fail on a fresh Python with `ModuleNotFoundError: No module named 'yaml'`.

```bash
uv run {mergeCccExclusionsHelper} \
    --project-root "{project-root}" \
    --skills-output-folder "{skills_output_folder}" \
    --forge-data-folder "{forge_data_folder}"
```

The script (see `src/shared/scripts/skf-merge-ccc-exclusions.py` docstring for the full schema) builds the SKF exclusion list (4 always-include hardcoded patterns + 2 conditional from validated config), applies the PR #248 validation rules to reject empty / absolute / glob-meta config values with actionable warnings, and performs an idempotent set-union merge into `{project-root}/.cocoindex_code/settings.yml`. User customizations are preserved. When the file does not exist yet (first-time setup before `ccc init`) the script creates it; when nothing new needs adding the script skips the write entirely (mtime preserved).

**Parse the JSON output and set context flags:**

- `{settings_yml_existed}` ← `settings_yml_existed`
- `{settings_yml_written}` ← `written`
- `{settings_yml_patterns_added}` ← `patterns_added`
- `{ccc_exclude_patterns}` ← derive from the script's behaviour: it always merges the 4 always-include patterns plus any of the 2 config-driven ones whose value passed validation. Step-02 needs this list to write `ccc_index.exclude_patterns` into forge-tier.yaml — read it from the script's `patterns_added_list` PLUS any already-present matching SKF patterns inferred from the input. Pragmatically: re-derive the list as `["**/_bmad", "**/_bmad-output", "**/.claude", "**/_skf-learn"]` plus `"**/{skills_output_folder}"` if no warning names `skills_output_folder` plus `"**/{forge_data_folder}"` if no warning names `forge_data_folder`.
- `{ccc_exclusion_warnings}` ← `warnings` (a list — step-04 folds them into the envelope's warnings array)

**If `{settings_yml_written}` is true** (new patterns merged into settings.yml): set `{needs_reindex: true}` — new exclusions require re-indexing for the index to reflect them. Display: "**CCC exclusions configured:** {patterns_added} SKF patterns applied to .cocoindex_code/settings.yml"

**If `{settings_yml_written}` is false** (idempotent re-run, all patterns already present): display nothing (exclusions already configured). Do NOT change `{needs_reindex}` — it stays at whatever section 2 set it to.

**Flow decision:**

- If `{needs_reindex}` is true: proceed to section 4
- If `{needs_reindex}` is false: proceed to section 5 (Auto-Proceed)

### 4. Create or Refresh CCC Index

**If `{ccc_daemon}` is `"stopped"` or `"healthy"`:** the `ccc index` command auto-starts the daemon when needed.

**If `{ccc_daemon}` is `"error"`:** attempt indexing anyway — errors will be caught below.

Run (CWD must be `{project-root}`):

```bash
ccc init
```

**If init fails** (project may already be initialized): continue — this is not an error. Note: when `{settings_yml_existed}` was false and `ccc init` just created the settings.yml, the merge in section 3 ran BEFORE ccc init. The script handles "no settings.yml exists" by creating one with just the SKF exclusions, which `ccc init` will then either preserve (if it merges) or overwrite (in which case the next workflow run re-merges). Either way the SKF exclusions end up in the file by the time `ccc index` runs the second time.

Before invoking `ccc index`, display: "**Building semantic index — this can take several minutes on large codebases (1000+ files). Run `ccc status` in another terminal to monitor progress.**" so the user does not assume the workflow has hung during the long-running call.

Then run:

```bash
ccc index
```

**Note:** `ccc index` can take several minutes on large codebases (1000+ files). Run with an extended timeout or in background mode. Use `ccc status` to verify completion — check that `Chunks` and `Files` counts are non-zero.

**If succeeds:**

- Run `ccc status` to get file count
- Store `{ccc_index_result: "created", ccc_indexed_path: {project-root}, ccc_last_indexed: {current ISO timestamp}, ccc_file_count: {count from ccc status}}`
- Display: "**CCC index created.** {ccc_file_count} files indexed for semantic discovery."

**If fails:**

- Store `{ccc_index_result: "failed", ccc_indexed_path: null, ccc_last_indexed: null, ccc_indexing_failed_reason: {error}}` (the failed-reason flag flows into step-04's envelope warnings)
- Display: "CCC indexing failed: {error}. Extraction will use direct AST scanning — semantic pre-ranking unavailable this session."
- Continue — this is NOT a workflow error

### 5. Auto-Proceed

After ccc index verification is complete (or skipped because ccc is unavailable), display "**Proceeding to write configuration...**", then load `{nextStepFile}`, read it fully, and execute it.

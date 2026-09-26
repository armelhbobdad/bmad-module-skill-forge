---
nextStepFile: 'write-config.md'
# `{mergeCccExclusionsHelper}` = first existing path in
# `{mergeCccExclusionsProbeOrder}`; halt if neither exists. The script owns
# `ccc init`, config-value validation, the collision check, the merge and
# prune of SKF patterns in .cocoindex_code/settings.yml, and the index
# decision — no prose fallback.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
---

<!-- Config: communicate in {communication_language}. User-visible status messages (indexing progress message) render in the user's language. -->

# Step 1b: CCC Index Verification

## STEP GOAL:

If ccc is available (`{ccc: true}` from step 1), invoke `{mergeCccExclusionsHelper}` to prepare `.cocoindex_code/settings.yml` (running `ccc init` when needed), keep its SKF exclusion patterns current, and decide whether the project index needs building; then build or refresh the index when it does. Store index state and exclusion results in context for step 2 to write into forge-tier.yaml and for step 4 to report.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## Rules

- The script owns `ccc init`, every `settings.yml` edit and the index decision — do not run `ccc init` or edit `settings.yml` yourself, and run `ccc index` only when `{ccc_index_action}` is `"index"`
- Do not fail the workflow if settings preparation or ccc indexing fails
- Every branch that leaves this step binds all four of `ccc_index_result`, `ccc_indexed_path`, `ccc_last_indexed`, and `ccc_file_count` — step 2 interpolates each bare into the `write-tools` JSON payload, so an unbound flag would emit its literal placeholder and fail the forge-tier.yaml write
- Display progress messages only when `{headless_mode}` and `{quiet_mode}` are both false

## MANDATORY SEQUENCE

### 1. Check Eligibility

**If `{ccc}` is false:** Set `{ccc_index_result: "none", ccc_indexed_path: null, ccc_last_indexed: null, ccc_file_count: null, ccc_exclude_patterns: null, ccc_exclusion_warnings: [], settings_yml_written: false, settings_yml_patterns_added: 0, settings_yml_patterns_removed: 0, gitignore_updated: false}` — `ccc_exclude_patterns: null` tells step 2 to keep the SKF pattern record already in forge-tier.yaml. Proceed directly to section 4 (Auto-Proceed) — no output, no messaging.

**If `{ccc}` is true:** continue to section 2, with or without `--ccc-skip-index` — the skip lane still prepares settings.yml; only the index build is skipped.

### 2. Prepare CCC Settings

SKF infrastructure and output directories must be excluded from the CCC index — they contain workflow instructions, build artifacts, and generated skills that pollute semantic search results with zero extraction value.

Forward `skills_output_folder` and `forge_data_folder` from `{project-root}/_bmad/skf/config.yaml` **verbatim** — the script resolves `{project-root}/...` template strings and validates the values itself. Pass `{ccc_index_fresh}` (from step 1) and `{ccc_skip_index}` as `true` or `false`. Invoke via `uv run`:

```bash
uv run {mergeCccExclusionsHelper} \
    --project-root "{project-root}" \
    --skills-output-folder "{skills_output_folder}" \
    --forge-data-folder "{forge_data_folder}" \
    --prior-state-from "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" \
    --index-fresh "{ccc_index_fresh}" \
    --skip-index "{ccc_skip_index}"
```

The script (see `src/shared/scripts/skf-merge-ccc-exclusions.py` docstring for the full schema) runs `ccc init` when settings.yml is missing, rebuilds a settings.yml that lacks the ccc default exclusions (keeping user entries), leaves out a configured folder that already holds files SKF did not generate, merges the SKF patterns, removes SKF patterns recorded in forge-tier.yaml that the current config no longer produces, never removes entries it did not add, and returns one `index_action`.

**If the script exits non-zero:** parse the stderr JSON `{"status":"error","message":...}` and set `{ccc_index_result: "failed", ccc_indexed_path: null, ccc_last_indexed: null, ccc_file_count: null, ccc_indexing_failed_reason: <message>, ccc_exclude_patterns: null, ccc_exclusion_warnings: [], settings_yml_written: false, settings_yml_patterns_added: 0, settings_yml_patterns_removed: 0, gitignore_updated: false}`, then proceed to section 4. Do not run `ccc index`.

**Otherwise parse the JSON output and set context flags:**

- `{ccc_index_action}` ← `index_action`
- `{settings_yml_written}` ← `written`
- `{settings_yml_patterns_added}` ← `patterns_added`
- `{settings_yml_patterns_removed}` ← `patterns_removed`
- `{gitignore_updated}` ← `gitignore_updated`
- `{ccc_exclude_patterns}` ← `effective_patterns` (a list or null — consume verbatim; null tells step 2 to keep the record already in forge-tier.yaml)
- `{ccc_exclusion_warnings}` ← `warnings` (a list — step 4 shows it in the report and folds it into the envelope's warnings)
- `{ccc_settings_error}` ← `not_ready_reason`

**Act on `{ccc_index_action}`:**

- `"keep"` → set `{ccc_index_result: "fresh", ccc_indexed_path: {project-root}, ccc_last_indexed: {previous_ccc_last_indexed}, ccc_file_count: {previous_ccc_file_count}}` (carried over from the prior forge-tier.yaml by step 1 — nothing re-counts on this path), then proceed to section 4
- `"skip"` → set `{ccc_index_result: "skipped", ccc_indexed_path: null, ccc_last_indexed: null, ccc_file_count: null}` (the envelope's `ccc_index.status` becomes `"skipped"`, so pipelines can tell an opt-out from a failure), then proceed to section 4
- `"fail"` → set `{ccc_index_result: "failed", ccc_indexed_path: null, ccc_last_indexed: null, ccc_file_count: null, ccc_indexing_failed_reason: {ccc_settings_error}}`, then proceed to section 4. Do not run `ccc index`: without a project settings.yml, ccc would create one at the enclosing git root and index it without the SKF exclusions
- `"index"` → proceed to section 3

### 3. Build or Refresh the CCC Index

**If `{ccc_daemon}` is `"stopped"` or `"healthy"`:** the `ccc index` command auto-starts the daemon when needed.

**If `{ccc_daemon}` is `"error"`:** attempt indexing anyway — errors will be caught below.

Unless `{headless_mode}` or `{quiet_mode}` is true, display: "**Building semantic index — this can take several minutes on large codebases (1000+ files). Run `ccc status` in another terminal to monitor progress.**"

```bash
cd "{project-root}" && ccc index
```

Run with an extended timeout or in background mode. Use `ccc status` to verify completion — check that `Chunks` and `Files` counts are non-zero.

**If it succeeds:** run `cd "{project-root}" && ccc status` to get the file count, then set `{ccc_index_result: "created", ccc_indexed_path: {project-root}, ccc_last_indexed: {current ISO timestamp}, ccc_file_count: {count from ccc status}}`. Unless `{headless_mode}` or `{quiet_mode}` is true, display "**CCC index created.** {ccc_file_count} files indexed for semantic discovery."

**If it fails:** set `{ccc_index_result: "failed", ccc_indexed_path: null, ccc_last_indexed: null, ccc_file_count: null, ccc_indexing_failed_reason: {error}}` — replace any single quote in `{error}` with a backtick, since step 4 embeds it in a single-quoted payload. Unless `{headless_mode}` or `{quiet_mode}` is true, display "CCC indexing failed: {error}. Extraction will use direct AST scanning — semantic pre-ranking unavailable this session." Continue — this is not a workflow error.

### 4. Auto-Proceed

Unless `{headless_mode}` or `{quiet_mode}` is true, display "**Proceeding to write configuration...**". Then load `{nextStepFile}`, read it fully, and execute it.

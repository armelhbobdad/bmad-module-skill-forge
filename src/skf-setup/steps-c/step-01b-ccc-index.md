---
nextStepFile: './step-02-write-config.md'
---

# Step 1b: CCC Index Verification

## STEP GOAL:

If ccc is available (`{ccc: true}` from step-01), configure CCC exclusion patterns for SKF infrastructure directories, verify that the ccc index exists for the project root, and create or refresh it if needed. Store index state and exclusion patterns in context for step-02 to write into forge-tier.yaml.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## Rules

- Focus only on ccc index verification and creation
- Do not display skip messages for Quick/Forge tiers
- Do not fail the workflow if ccc indexing fails
- Do not re-index if ccc index already exists and is fresh, unless new exclusion patterns were applied

## MANDATORY SEQUENCE

### 1. Check Eligibility

Read `{ccc}` from step-01 context.

**If `{ccc}` is false:** Set `{ccc_index_result: "none", ccc_indexed_path: null, ccc_last_indexed: null, ccc_exclude_patterns: []}`. Proceed directly to section 4 (Auto-Proceed) — no output, no messaging.

**If `{ccc}` is true:** Continue to section 2.

### 2. Check Existing Index State

Read existing forge-tier.yaml at `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (if it exists from a previous run).

Read `staleness_threshold_hours` from `ccc_index.staleness_threshold_hours` in the existing forge-tier.yaml (default: 24 if not present or not a number). Use this value for the freshness check below.

Check the `ccc_index` section:
- If `ccc_index.indexed_path` matches `{project-root}` AND `ccc_index.status` is `"fresh"` or `"created"`:
  - Check freshness: if `ccc_index.last_indexed` is within `staleness_threshold_hours` of now → index is fresh
  - Store `{ccc_index_result: "fresh", ccc_indexed_path: {project-root}, ccc_last_indexed: {existing timestamp}}`
  - Set `{needs_reindex: false}` — proceed to section 2b (exclusions must still be configured)

- If `ccc_index.indexed_path` matches `{project-root}` but timestamp is older than threshold:
  - Set `{needs_reindex: true}` — proceed to section 2b then section 3

- If `ccc_index` is missing, has null values, or path doesn't match:
  - Set `{needs_reindex: true}` — proceed to section 2b then section 3

### 2b. Configure CCC Exclusions

SKF infrastructure and output directories must be excluded from the CCC index — they contain workflow instructions, build artifacts, and generated skills that pollute semantic search results with zero extraction value.

**Build the SKF exclusion list:**

1. Use `{skills_output_folder}` and `{forge_data_folder}` from the workflow activation context (resolved in On Activation from `{project-root}/_bmad/skf/config.yaml`).

2. Assemble the exclusion patterns using `**/` prefix format (matching `.cocoindex_code/settings.yml` convention — e.g., `**/node_modules`).

   **Always include** these four hardcoded patterns:
   - `**/_bmad` — SKF framework module (workflows, agents, knowledge files)
   - `**/_bmad-output` — Build output artifacts
   - `**/.claude` — Claude Code configuration
   - `**/_skf-learn` — SKF learning materials

   **Conditionally include** these two patterns from activation context, but only after **validating the source value** to avoid producing malformed globs that would silently exclude the entire repository from indexing:
   - `**/{skills_output_folder}` — Generated skill files
   - `**/{forge_data_folder}` — Compilation workspace

   **Validation rules** — for each of `{skills_output_folder}` and `{forge_data_folder}`, before interpolating into the `**/{value}` pattern, reject the value (skip the pattern entirely) and append a warning to `{ccc_exclusion_warnings}` if any of:

   - The value is empty or whitespace-only (would produce `**/` — matches every path, ccc would index nothing).
   - The value begins with `/`, `~/`, or `./` (absolute or anchored path — produces `**//abs/path` or `**/./rel`, malformed glob).
   - The value contains glob meta-characters (`*`, `?`, `[`) — interpolation collides with the surrounding pattern syntax.

   The warning text should name the offending config key, the bad value (quoted verbatim), and the rejection reason — e.g. `"skills_output_folder is an absolute path; refused for ccc exclusion because interpolating it would produce a malformed glob — fix the value in {project-root}/_bmad/skf/config.yaml"`. Step-04 surfaces these in the JSON envelope `warnings` array.

3. Store `{ccc_exclude_patterns}` (the validated list — possibly only the four always-include patterns if both config values were rejected) in context for step-02 to write into forge-tier.yaml.

**Apply exclusions to settings.yml:**

Check if `{project-root}/.cocoindex_code/settings.yml` exists. Set `{settings_yml_existed: true}` if it does, `{settings_yml_existed: false}` if not.

If `{settings_yml_existed}` is true (from a previous `ccc init` run):

1. Read `settings.yml`
2. For each pattern in `{ccc_exclude_patterns}`: if the pattern is NOT already present in `exclude_patterns`, append it and set `{exclusions_changed: true}`
3. If `{exclusions_changed}`: write the updated `settings.yml` back, set `{needs_reindex: true}` (new exclusions require re-indexing), set `{settings_yml_written: true}` and `{settings_yml_patterns_added: count}` for step-04 reporting, display: "**CCC exclusions configured:** {count} SKF patterns applied to .cocoindex_code/settings.yml"
4. If no new patterns needed: display nothing (exclusions already configured); set `{settings_yml_written: false}`

This preserves any existing user customizations and default exclusions while ensuring SKF directories are filtered out.

If `{settings_yml_existed}` is false: the exclusions will be applied after `ccc init` in section 3.

**Flow decision:**
- If `{needs_reindex}` is true: proceed to section 3
- If `{needs_reindex}` is false: proceed to section 4 (Auto-Proceed)

### 3. Create or Refresh CCC Index

**If `{ccc_daemon}` is `"stopped"` or `"healthy"`:**

The `ccc index` command auto-starts the daemon when needed. Proceed with indexing below.

**If `{ccc_daemon}` is `"error"`:**

Attempt indexing anyway — errors will be caught below.

Run (CWD must be `{project-root}`):
```bash
ccc init
```

**If init fails** (project may already be initialized): continue — this is not an error.

**Apply SKF exclusion patterns (if not already applied in section 2b):**

If `{settings_yml_existed}` is false (first-time setup — `ccc init` just created it), apply exclusions now:

1. Read `{project-root}/.cocoindex_code/settings.yml` (created by `ccc init`)
2. For each pattern in `{ccc_exclude_patterns}`: if the pattern is NOT already present in `exclude_patterns`, append it (track `{count}` of patterns added)
3. Write the updated `settings.yml` back. Set `{settings_yml_written: true}` and `{settings_yml_patterns_added: count}` for step-04 reporting.
4. Display: "**CCC exclusions configured:** {count} SKF patterns applied to .cocoindex_code/settings.yml"

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
- Store `{ccc_index_result: "failed", ccc_indexed_path: null, ccc_last_indexed: null}`
- Display: "CCC indexing failed: {error}. Extraction will use direct AST scanning — semantic pre-ranking unavailable this session."
- Continue — this is NOT a workflow error

### 4. Auto-Proceed

After ccc index verification is complete (or skipped because ccc is unavailable), display "**Proceeding to write configuration...**", then load `{nextStepFile}`, read it fully, and execute it.


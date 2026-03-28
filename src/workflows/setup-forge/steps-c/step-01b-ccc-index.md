---
name: 'step-01b-ccc-index'
description: 'Ensure ccc project index exists — Forge+ and Deep tiers when ccc is available'

nextStepFile: './step-02-write-config.md'
---

# Step 1b: CCC Index Verification

## STEP GOAL:

If ccc is available (`{ccc: true}` from step-01), configure CCC exclusion patterns for SKF infrastructure directories, verify that the ccc index exists for the project root, and create or refresh it if needed. Store index state and exclusion patterns in context for step-02 to write into forge-tier.yaml.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 🎯 Execute all operations autonomously — no user interaction

### Role Reinforcement:

- ✅ You are a system executor verifying the ccc index state
- ✅ ccc indexing failure is never a workflow error — degrade gracefully
- ✅ No negative messaging for tiers that skip this step

### Step-Specific Rules:

- 🎯 Focus only on ccc index verification and creation
- 🚫 FORBIDDEN to display skip messages for Quick/Forge tiers
- 🚫 FORBIDDEN to fail the workflow if ccc indexing fails
- 🚫 FORBIDDEN to re-index if ccc index already exists and is fresh (< staleness threshold) UNLESS new exclusion patterns were applied to settings.yml

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Store ccc index state in context for step-02
- 🚫 FORBIDDEN to write forge-tier.yaml — that is step-02's job

## CONTEXT BOUNDARIES:

- Available: {ccc} boolean and {ccc_daemon} status from step-01
- Available: {calculated_tier} from step-01
- Available: existing forge-tier.yaml may contain prior `ccc_index` state
- Focus: ccc index state verification and creation only
- Dependencies: step-01 must have completed with tool detection results

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

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

1. Read `{project-root}/_bmad/_config/skf-manifest.yaml` to resolve configurable paths:
   - `skills_output_folder` (default: `skills` if manifest is missing or field is absent)
   - `forge_data_folder` (default: `forge-data` if manifest is missing or field is absent)

2. Assemble the exclusion patterns using `**/` prefix format (matching `.cocoindex_code/settings.yml` convention — e.g., `**/node_modules`):
   - `**/_bmad` — SKF framework module (workflows, agents, knowledge files)
   - `**/_bmad-output` — Build output artifacts
   - `**/.claude` — Claude Code configuration
   - `**/_skf-learn` — SKF learning materials
   - `**/{skills_output_folder}` — Generated skill files (resolved from manifest)
   - `**/{forge_data_folder}` — Compilation workspace (resolved from manifest)

3. Store `{ccc_exclude_patterns}` in context for step-02 to write into forge-tier.yaml.

**Apply exclusions to settings.yml:**

Check if `{project-root}/.cocoindex_code/settings.yml` exists. Set `{settings_yml_existed: true}` if it does, `{settings_yml_existed: false}` if not.

If `{settings_yml_existed}` is true (from a previous `ccc init` run):

1. Read `settings.yml`
2. For each pattern in `{ccc_exclude_patterns}`: if the pattern is NOT already present in `exclude_patterns`, append it and set `{exclusions_changed: true}`
3. If `{exclusions_changed}`: write the updated `settings.yml` back, set `{needs_reindex: true}` (new exclusions require re-indexing), display: "**CCC exclusions configured:** {count} SKF patterns applied to .cocoindex_code/settings.yml"
4. If no new patterns needed: display nothing (exclusions already configured)

This preserves any existing user customizations and default exclusions while ensuring SKF directories are filtered out.

If `{settings_yml_existed}` is false: the exclusions will be applied after `ccc init` in section 3.

**Flow decision:**
- If `{needs_reindex}` is true: proceed to section 3
- If `{needs_reindex}` is false: proceed to section 4 (Auto-Proceed)

### 3. Create or Refresh CCC Index

**If `{ccc_daemon}` is `"stopped"` or undefined (healthy daemon where no explicit state was recorded):**

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
2. For each pattern in `{ccc_exclude_patterns}`: if the pattern is NOT already present in `exclude_patterns`, append it
3. Write the updated `settings.yml` back
4. Display: "**CCC exclusions configured:** {count} SKF patterns applied to .cocoindex_code/settings.yml"

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

"**Proceeding to write configuration...**"

#### Menu Handling Logic:

- After ccc index check completes (or is skipped), immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after ccc index verification

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN ccc index verification is complete (or step is skipped for ccc unavailable) will you load and read fully `{nextStepFile}` to execute the configuration write step.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- ccc unavailable: skipped silently with no output, context variables set to null/none
- ccc available with fresh index: verified freshness, exclusions configured, skipped re-index, context variables set
- ccc available with stale/missing index: exclusions configured, index created, context variables set with fresh timestamp
- ccc indexing fails: logged gracefully, workflow continues, context variables set to failed/null
- Auto-proceeded to step-02

### ❌ SYSTEM FAILURE:

- Displaying skip messages when ccc is unavailable
- Halting the workflow on ccc index failure
- Re-indexing when index is already fresh and path matches (unless exclusion patterns changed)
- Writing forge-tier.yaml (that is step-02's responsibility)
- Not storing ccc index context variables for step-02
- Indexing without configuring SKF exclusion patterns in `.cocoindex_code/settings.yml`
- Overwriting user customizations in `.cocoindex_code/settings.yml` instead of appending

**Master Rule:** CCC indexing is always best-effort. Failures degrade gracefully. The workflow never halts over ccc issues.

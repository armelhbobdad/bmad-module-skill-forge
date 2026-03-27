---
name: 'step-01b-ccc-index'
description: 'Ensure ccc project index exists — Forge+ and Deep tiers when ccc is available'

nextStepFile: './step-02-write-config.md'
---

# Step 1b: CCC Index Verification

## STEP GOAL:

If ccc is available (`{ccc: true}` from step-01), verify that the ccc index exists for the project root. If no index exists, create it. Store index state in context for step-02 to write into forge-tier.yaml.

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
- 🚫 FORBIDDEN to re-index if ccc index already exists and is fresh (< staleness threshold)

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

**If `{ccc}` is false:** Set `{ccc_index_result: "none", ccc_indexed_path: null, ccc_last_indexed: null}`. Proceed directly to section 4 (Auto-Proceed) — no output, no messaging.

**If `{ccc}` is true:** Continue to section 2.

### 2. Check Existing Index State

Read existing forge-tier.yaml at `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (if it exists from a previous run).

Check the `ccc_index` section:
- If `ccc_index.indexed_path` matches `{project-root}` AND `ccc_index.status` is `"fresh"`:
  - Check freshness: if `ccc_index.last_indexed` is within `staleness_threshold_hours` (default 24h) of now → index is fresh
  - Store `{ccc_index_result: "fresh", ccc_indexed_path: {project-root}, ccc_last_indexed: {existing timestamp}}`
  - Proceed to section 4

- If `ccc_index.indexed_path` matches `{project-root}` but timestamp is older than threshold:
  - Note index is stale — proceed to section 3 for re-index (section 3 will overwrite `ccc_index_result` to `"created"` or `"failed"`)

- If `ccc_index` is missing, has null values, or path doesn't match:
  - Proceed to section 3 for initial index

### 3. Create or Refresh CCC Index

**If `{ccc_daemon}` is `"stopped"` or undefined (healthy daemon where no explicit state was recorded):**

The `ccc index` command auto-starts the daemon when needed. Proceed with indexing below.

**If `{ccc_daemon}` is `"error"`:**

Attempt indexing anyway — errors will be caught below.

Run:
```bash
ccc init {project-root}
```

**If init fails** (project may already be initialized): continue — this is not an error.

Then run:
```bash
ccc index
```

**If succeeds:**
- Run `ccc status` to get file count
- Store `{ccc_index_result: "created", ccc_indexed_path: {project-root}, ccc_last_indexed: {current ISO timestamp}, ccc_file_count: {count from status}}`
- Display: "**CCC index created.** {file_count} files indexed for semantic discovery."

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
- ccc available with fresh index: verified freshness, skipped re-index, context variables set
- ccc available with stale/missing index: index created, context variables set with fresh timestamp
- ccc indexing fails: logged gracefully, workflow continues, context variables set to failed/null
- Auto-proceeded to step-02

### ❌ SYSTEM FAILURE:

- Displaying skip messages when ccc is unavailable
- Halting the workflow on ccc index failure
- Re-indexing when index is already fresh and path matches
- Writing forge-tier.yaml (that is step-02's responsibility)
- Not storing ccc index context variables for step-02

**Master Rule:** CCC indexing is always best-effort. Failures degrade gracefully. The workflow never halts over ccc issues.

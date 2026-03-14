---
name: 'step-03-auto-index'
description: 'Verify and clean QMD collections against the forge-tier.yaml registry (Deep tier only)'

nextStepFile: './step-04-report.md'
---

# Step 3: QMD Collection Hygiene

## STEP GOAL:

If the detected tier is Deep, verify the health of existing QMD collections by cross-referencing them against the `qmd_collections` registry in `forge-tier.yaml`. Identify orphaned collections (in QMD but not in registry) and stale registry entries (in registry but collection missing from QMD). Prompt the user before removing orphaned collections.

For Quick and Forge tiers, skip silently and proceed.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 🎯 Execute all operations autonomously — minimal user interaction (only prompt before deletion)

### Role Reinforcement:

- ✅ You are a system executor performing QMD collection maintenance
- ✅ Graceful degradation is paramount — never fail the workflow over hygiene checks
- ✅ No negative messaging — do not mention what non-Deep tiers are missing

### Step-Specific Rules:

- 🎯 Focus only on verifying and cleaning QMD collections (Deep tier) or graceful skip (other tiers)
- 🚫 FORBIDDEN to display "missing" or "skipped" messages for non-Deep tiers
- 🚫 FORBIDDEN to fail the workflow if QMD hygiene encounters errors
- 🚫 FORBIDDEN to create new QMD collections — that responsibility belongs to create-skill
- 🚫 FORBIDDEN to silently delete collections — always prompt user before removal
- 💬 If hygiene fails: log the issue, note that it can be retried, continue

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 QMD hygiene only verifies and cleans — it does NOT index new content
- 📖 Use {calculated_tier} from step-01 context
- 🚫 FORBIDDEN to attempt hygiene for Quick or Forge tiers

## CONTEXT BOUNDARIES:

- Available: {calculated_tier} from step-01, forge-tier.yaml written in step-02
- Available: {project_name} from workflow config
- Focus: QMD collection verification and cleanup only
- Limits: only run if Deep tier
- Dependencies: step-02 must have completed (forge-tier.yaml exists with qmd_collections registry)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tier

Read `{calculated_tier}` from context.

**If tier is NOT Deep:** Proceed directly to section 6 (Auto-Proceed) — no output, no messaging.

**If tier IS Deep:** Continue to section 2.

### 2. Load Registry and QMD State

Read the `qmd_collections` array from `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml`.

List live QMD collections:
```bash
qmd collection list
```

**Store both lists for cross-reference:**
- `{registry_collections}` — entries from forge-tier.yaml qmd_collections
- `{live_collections}` — collections currently in QMD

**Error handling:** If `qmd collection list` fails, log the error, store `{hygiene_result: "qmd_unavailable"}`, and proceed to section 6.

### 3. Cross-Reference and Classify

Compare the two lists:

**Healthy** — collection exists in both registry AND QMD:
- Mark as verified
- No action needed

**Orphaned** — collection exists in QMD but NOT in registry:
- These may be leftover from prior auto-indexing or manual indexing
- Flag for user-prompted removal

**Stale** — entry exists in registry but collection is missing from QMD:
- The QMD collection was deleted or lost
- Remove the stale entry from the registry

### 4. Handle Orphaned Collections

**If orphaned collections found:**

Display to user:
"**QMD Hygiene: Found {count} orphaned collection(s) not tracked in the forge registry:**

{list orphaned collection names}

These collections exist in QMD but are not managed by any skill workflow. They may be from a previous auto-index run or manual creation.

**[R]emove** orphaned collections — clean up QMD
**[K]eep** orphaned collections — leave them as-is"

**If user selects R (Remove):**
For each orphaned collection:
```bash
qmd collection remove {collection_name}
```
Log each removal.

**If user selects K (Keep):**
Skip removal. Log that orphaned collections were kept.

**If no orphaned collections:** Skip this section silently.

### 5. Handle Stale Registry Entries

**If stale registry entries found:**

Remove stale entries from the `qmd_collections` array in forge-tier.yaml.

Display: "**Cleaned {count} stale registry entry/entries** (collection no longer exists in QMD)."

Update forge-tier.yaml with the cleaned registry.

**If no stale entries:** Skip this section silently.

### 6. Store Hygiene Results and Auto-Proceed

Store in context for step-04 reporting:
```
{hygiene_result: "completed"|"skipped"|"qmd_unavailable"}
{hygiene_healthy: count}
{hygiene_orphaned_removed: count}
{hygiene_orphaned_kept: count}
{hygiene_stale_cleaned: count}
```

"**Proceeding to forge status report...**"

#### Menu Handling Logic:

- After hygiene completes (or is skipped), immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This step has one optional user interaction (orphan removal prompt)
- If no orphans found, this is an auto-proceed step
- Proceed directly to next step after hygiene or skip

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the hygiene check has been performed (or skipped for non-Deep tiers) will you load and read fully `{nextStepFile}` to execute the report step.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Deep tier: forge-tier.yaml registry cross-referenced with live QMD collections
- Healthy collections identified and verified
- Orphaned collections flagged and user prompted before removal
- Stale registry entries cleaned from forge-tier.yaml
- Hygiene results stored for step-04 reporting
- Quick/Forge tier: skipped silently with no negative messaging
- Workflow continues regardless of hygiene outcome
- Auto-proceeded to step-04

### ❌ SYSTEM FAILURE:

- Creating new QMD collections (that's create-skill's responsibility)
- Silently deleting collections without user prompt
- Attempting QMD hygiene for Quick or Forge tiers
- Displaying "skipped" or "missing" messages for non-Deep tiers
- Halting the workflow due to QMD hygiene failure
- Indexing project directories (old auto-index behavior — removed)
- Not proceeding to step-04 after this step

**Master Rule:** This step ONLY verifies and cleans. It never indexes new content. QMD collection creation is the responsibility of create-skill. Non-Deep tiers skip silently. Always prompt before removing orphaned collections.

---
nextStepFile: './step-04-report.md'
---

# Step 3: QMD Collection Hygiene

## STEP GOAL:

If the detected tier is Deep, verify the health of existing QMD collections by cross-referencing them against the `qmd_collections` registry in `forge-tier.yaml`. Identify orphaned collections (in QMD but not in registry) and stale registry entries (in registry but collection missing from QMD). Prompt the user before removing orphaned collections.

For Quick and Forge tiers, skip silently and proceed (QMD is not available at those tiers). For Forge+ tier, skip QMD hygiene but the step routes correctly to the next step.

## Rules

- Focus only on verifying and cleaning QMD collections (Deep tier) or graceful skip (other tiers)
- Do not display negative framing for non-Deep tiers
- Do not fail the workflow if QMD hygiene encounters errors
- Do not create new QMD collections — that belongs to create-skill
- Do not silently delete collections — always prompt user before removal

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tier

Read `{calculated_tier}` from context.

**If tier is Quick or Forge:** Set `{ccc_registry_stale_cleaned: 0}`. Proceed directly to section 6 (Auto-Proceed) — no output, no messaging.

**If tier is Forge+:** Skip QMD hygiene (qmd is not available at Forge+). Proceed directly to section 5b (CCC Index Registry Hygiene) — no QMD output, no messaging.

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

### 5b. CCC Index Registry Hygiene (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml (regardless of whether QMD hygiene ran):**

Read the `ccc_index_registry` array from forge-tier.yaml.

For each entry, verify the indexed path still exists on disk:

**Healthy** — path exists: no action needed.

**Stale** — path does not exist (source directory removed or moved):
- Remove the stale entry from `ccc_index_registry`
- Log: "Removed stale CCC index registry entry: {path} (path no longer exists)"

Update forge-tier.yaml with the cleaned registry.

Store `{ccc_registry_stale_cleaned: count}` in context for step-04 reporting.

**IF `tools.ccc` is false:** Skip this section silently.

### 6. Store Hygiene Results and Auto-Proceed

Store in context for step-04 reporting:
```
{hygiene_result: "completed"|"skipped"|"qmd_unavailable"}
{hygiene_healthy: count}
{hygiene_orphaned_removed: count}
{hygiene_orphaned_kept: count}
{hygiene_stale_cleaned: count}
{ccc_registry_stale_cleaned: count}
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


---
nextStepFile: 'severity-classify.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder: §4 saves the findings step 5 classifies.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Semantic Diff

## STEP GOAL:

Compare what the skill documents about each export (retrieved from its QMD extraction collection) against the current source under `{source_root}` to detect meaning-level changes that structural diff cannot catch. This step executes ONLY at Deep tier: at Quick, Forge, and Forge+ tiers, it appends a skip notice and auto-proceeds.

## Rules

- At Quick/Forge/Forge+ tier, skip the entire analysis — append the skip notice only
- Find meaning-level changes in the current source; QMD only retrieves what the skill says. Do not repeat structural findings from Step 03
- Do not classify severity (Step 05)
- Use subprocess Pattern 3 when available for §2 items 2 to 4 (the QMD query and the source reads); if unavailable, run them in the main thread

## MANDATORY SEQUENCE

### 1. Check Forge Tier

**If forge tier is Quick, Forge, or Forge+:**

Append to {outputFile}:

```markdown
## Semantic Drift

**Status:** Skipped — Semantic diff requires Deep tier (current tier: {tier})

Semantic analysis checks what the skill documents (retrieved from its QMD collection) against the current source for meaning-level changes that structural diff cannot detect. To enable semantic diff, run setup with QMD available to unlock Deep tier.
```

Update frontmatter: append `'semantic-diff'` to `stepsCompleted`

"**Semantic diff skipped (requires Deep tier). Proceeding to severity classification...**"

→ Auto-proceed to {nextStepFile}

**If forge tier is Deep:**

Continue to section 2.

### 2. Query Original Knowledge Context

Run item 1 in the main thread, because only the main thread can end this step, then launch a subprocess (Pattern 3, data operations) for items 2 to 4:
1. Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`. Find the entry where `skill_name` matches `{skill_name}` AND `type` is `"extraction"`. Three cases must be handled distinctly — collapsing them into "found vs. not found" silently degrades semantic diff when a collection is registered but never indexed.

   - **Registry entry missing.** Log: "No QMD extraction collection found for `{skill_name}`. Semantic diff skipped." Append a `## Semantic Drift` section holding `**Status:** Skipped: no QMD extraction collection is registered for {skill_name}` to {outputFile}, append `'semantic-diff'` to `stepsCompleted`, and auto-proceed to {nextStepFile}.
   - **Registry entry present but collection empty.** Run a pre-query probe — `qmd ls {collection_name}` (CLI) or the equivalent MCP call. If it reports zero files (`Files: 0 (updated never)` or an empty listing), the collection is registered but has never been indexed. Do **not** proceed to querying — queries will return nothing and the step would silently degrade.
     - Log: "QMD collection `{collection_name}` is registered but empty. Run `qmd update` to (re-)index `{collection.path}`, then re-audit for full Deep-tier semantic coverage."
     - Fall through to the **direct-content fallback** below instead of skipping outright.
   - **Registry entry present and populated.** Use the `name` field from the registry entry as the collection to query. Proceed to bullet 2.

   **Direct-content fallback** (used when the collection is registered but empty): read what the skill documents about each export from `SKILL.md` and `references/*.md` of the audited skill in place of item 2's query, then run items 3 and 4 on those claims, checking the current source under `{source_root}` with the Deep-tier AST tooling this step already requires (ast_bridge; see step 2 §1 "Deep tier"). This fallback is reachable only from Deep tier: §1 short-circuits Quick/Forge/Forge+ before §2 runs, so AST tooling is guaranteed available here. Record findings with confidence label `T1-low-fallback` rather than T2: the claims come from reading the skill's files, not from its QMD collection. The step's output schema is otherwise unchanged; set `qmd_collection = null` in the Semantic Drift header and annotate: "Semantic diff ran in direct-content fallback mode: QMD collection was registered but empty."

2. Query the collection for what the skill documents about each export (usage, conventions, dependencies, architecture): the original side
3. For each claim, read the export's current definition and call sites under `{source_root}` at the file and line `{forge_version}/extraction-snapshot.json` records for it: the current side (an export the snapshot no longer holds is a removed export step 3 already reports: skip it)
4. Return each claim the source no longer supports with that file:line

### 3. Compare Knowledge Context

For each export in the skill, compare original context (from skill creation, item 2) against the current source under `{source_root}` (item 3):

**Detect:**
- **New patterns:** Usage patterns that have emerged since skill was created
- **Changed conventions:** Project conventions that have shifted (e.g., new error handling pattern)
- **Dependency shifts:** Libraries or modules that exports now depend on differently
- **Architectural changes:** Structural reorganization affecting how exports relate to each other
- **Deprecated patterns:** Usage patterns documented in skill that are no longer followed

For each finding, record:
- What changed (description)
- Evidence (the current source file:line; a claim with no source line is not recorded)
- Affected exports
- Confidence: T2

### 4. Compile Semantic Drift Section

Append to {outputFile}:

```markdown
## Semantic Drift

**Method:** the skill's claims (from QMD) checked against the current source (Deep tier)
**QMD Collection:** {collection_name}

### New Patterns Detected ({count})

| Pattern | Description | Affected Exports | Evidence | Confidence |
|---------|------------|-----------------|----------|------------|
| {pattern} | {description} | {exports} | {evidence} | T2 |

### Changed Conventions ({count})

| Convention | Before | After | Affected Exports | Evidence | Confidence |
|-----------|--------|-------|-----------------|----------|------------|
| {convention} | {old} | {new} | {exports} | {evidence} | T2 |

### Dependency Shifts ({count})

| Export | Original Dependencies | Current Dependencies | Change | Evidence | Confidence |
|--------|---------------------|---------------------|--------|----------|------------|
| {export} | {old_deps} | {new_deps} | {description} | {evidence} | T2 |

### Architectural Changes ({count})

| Change | Description | Affected Exports | Evidence | Confidence |
|--------|-------------|------------------|----------|------------|
| {change} | {description} | {exports} | {evidence} | T2 |

### Deprecated Patterns ({count})

| Pattern | Documented In Skill | Current Status | Evidence | Confidence |
|---------|-------------------|----------------|----------|------------|
| {pattern} | {skill_reference} | {status} | {evidence} | T2 |

### Summary

| Category | Count |
|----------|-------|
| New patterns | {count} |
| Changed conventions | {count} |
| Dependency shifts | {count} |
| Architectural changes | {count} |
| Deprecated patterns | {count} |
| **Total Semantic Items** | {total} |
```

Save the same rows to `{auditDataFolder}/semantic-findings.json`: step 5 classifies this file, not the tables. It is a JSON array with one object per row, `{"type": "semantic", "category", "name", "detail", "file", "line", "confidence"}`. `category` is its table's: New Patterns `pattern`, Changed Conventions `convention`, Dependency Shifts `dependency`, Architectural Changes `architecture` and Deprecated Patterns `deprecated_pattern`. `name` is the row's first cell, `detail` its description or change, `file` and `line` the current source line its evidence cites, and `confidence` the row's (T2, or T1-low-fallback).

### 5. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'semantic-diff'` to `stepsCompleted`. Once the ## Semantic Drift section (or skip notice) has been appended, load, read fully, and execute `{nextStepFile}` (severity classification).


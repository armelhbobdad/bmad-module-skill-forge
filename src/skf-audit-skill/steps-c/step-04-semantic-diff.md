---
nextStepFile: './step-05-severity-classify.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
---

# Step 4: Semantic Diff

## STEP GOAL:

Compare QMD knowledge context between the original skill creation and current state to detect meaning-level changes that structural diff cannot catch. This step executes ONLY at Deep tier — at Quick, Forge, and Forge+ tiers, it appends a skip notice and auto-proceeds.

## Rules

- CONDITIONAL: Skip entire analysis at Quick/Forge/Forge+ tier — append skip notice only
- Focus only on semantic/meaning-level changes via QMD context — do not repeat structural findings from Step 03
- Do not classify severity (Step 05)
- Use subprocess Pattern 3 when available for QMD queries; if unavailable, query in main thread

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Forge Tier

**IF forge tier is Quick, Forge, or Forge+:**

Append to {outputFile}:

```markdown
## Semantic Drift

**Status:** Skipped — Semantic diff requires Deep tier (current tier: {tier})

Semantic analysis compares QMD knowledge context for meaning-level changes that structural diff cannot detect. To enable semantic diff, run setup with QMD available to unlock Deep tier.
```

Update frontmatter: append `'step-04-semantic-diff'` to `stepsCompleted`

"**Semantic diff skipped (requires Deep tier). Proceeding to severity classification...**"

→ Auto-proceed to {nextStepFile}

**IF forge tier is Deep:**

Continue to section 2.

### 2. Query Original Knowledge Context

Launch a subprocess (Pattern 3 — data operations) that:
1. Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`. Find the entry where `skill_name` matches `{skill_name}` AND `type` is `"extraction"`. Three cases must be handled distinctly — collapsing them into "found vs. not found" silently degrades semantic diff when a collection is registered but never indexed.

   - **Registry entry missing.** Log: "No QMD extraction collection found for `{skill_name}`. Semantic diff skipped." → Auto-proceed to {nextStepFile}.
   - **Registry entry present but collection empty.** Run a pre-query probe — `qmd ls {collection_name}` (CLI) or the equivalent MCP call. If it reports zero files (`Files: 0 (updated never)` or an empty listing), the collection is registered but has never been indexed. Do **not** proceed to querying — queries will return nothing and the step would silently degrade.
     - Log: "QMD collection `{collection_name}` is registered but empty. Run `qmd update` to (re-)index `{collection.path}`, then re-audit for full Deep-tier semantic coverage."
     - Fall through to the **direct-content fallback** below instead of skipping outright.
   - **Registry entry present and populated.** Use the `name` field from the registry entry as the collection to query. Proceed to bullet 2.

   **Direct-content fallback** (used when the collection is registered but empty): load `SKILL.md` and `references/*.md` from the audited skill, then spot-check each documented export against the current source tree under `{source_root}` using the Deep-tier AST tooling this step already requires (ast_bridge; see step-02 §1 "Deep tier"). This fallback is reachable only from Deep tier — §1 short-circuits Quick/Forge/Forge+ before §2 runs, so AST tooling is guaranteed available here. Record findings with confidence label `T1-low-fallback` rather than T2 — this is direct content inspection, not QMD-backed semantic analysis. The step's output schema is otherwise unchanged; set `qmd_collection = null` in the Semantic Drift header and annotate: "Semantic diff ran in direct-content fallback mode — QMD collection was registered but empty."

2. Queries for knowledge context around each export documented in the skill
3. Retrieves: usage patterns, conventions, architectural context, dependency relationships
4. Returns structured findings to parent

**If subprocess unavailable:** Query QMD in main thread.

### 3. Compare Knowledge Context

For each export in the skill, compare original context (from skill creation) against current context (from QMD):

**Detect:**
- **New patterns:** Usage patterns that have emerged since skill was created
- **Changed conventions:** Project conventions that have shifted (e.g., new error handling pattern)
- **Dependency shifts:** Libraries or modules that exports now depend on differently
- **Architectural changes:** Structural reorganization affecting how exports relate to each other
- **Deprecated patterns:** Usage patterns documented in skill that are no longer followed

For each finding, record:
- What changed (description)
- Evidence (QMD reference or source citation)
- Affected exports
- Confidence: T2

### 4. Compile Semantic Drift Section

Append to {outputFile}:

```markdown
## Semantic Drift

**Method:** QMD knowledge context comparison (Deep tier)
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

| Export | Original Dependencies | Current Dependencies | Change | Confidence |
|--------|---------------------|---------------------|--------|------------|
| {export} | {old_deps} | {new_deps} | {description} | T2 |

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
| Deprecated patterns | {count} |
| **Total Semantic Items** | {total} |
```

### 5. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'step-04-semantic-diff'` to `stepsCompleted`

### 6. Present MENU OPTIONS

Display: "**Semantic diff complete. {total} semantic drift items found. Proceeding to severity classification...**"

#### Menu Handling Logic:

- After semantic diff section is appended and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after completion

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Semantic Drift section (or skip notice) has been appended to {outputFile} will you then load and read fully `{nextStepFile}` to execute and begin severity classification.


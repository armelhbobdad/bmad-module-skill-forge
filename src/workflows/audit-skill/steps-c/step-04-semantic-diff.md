---
name: 'step-04-semantic-diff'
description: 'Compare QMD knowledge context for meaning-level changes (Deep tier only, skip at Quick/Forge/Forge+)'

nextStepFile: './step-05-severity-classify.md'
outputFile: '{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md'
---

# Step 4: Semantic Diff

## STEP GOAL:

Compare QMD knowledge context between the original skill creation and current state to detect meaning-level changes that structural diff cannot catch. This step executes ONLY at Deep tier — at Quick, Forge, and Forge+ tiers, it appends a skip notice and auto-proceeds.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor performing semantic analysis
- ✅ Semantic findings have T2 confidence — evidence-backed but not structurally absolute
- ✅ Distinguish clearly between structural facts (T1) and semantic observations (T2)

### Step-Specific Rules:

- 🎯 Focus only on semantic/meaning-level changes via QMD context
- 🚫 FORBIDDEN to classify severity — that happens in Step 05
- 🚫 FORBIDDEN to repeat structural findings from Step 03
- 💬 Use subprocess Pattern 3 (data operations — main thread Read + process in Claude Code, script in CLI) when available for QMD queries. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- ⚙️ If subprocess unavailable, query QMD in main thread
- 🔀 CONDITIONAL: Skip entire analysis at Quick/Forge/Forge+ tier — append skip notice only

## EXECUTION PROTOCOLS:

- 🎯 Check forge tier FIRST — skip if not Deep
- 💾 Append ## Semantic Drift section (or skip notice) to {outputFile}
- 📖 Update {outputFile} frontmatter stepsCompleted when complete
- 🚫 Only semantic findings — no structural or severity analysis

## CONTEXT BOUNDARIES:

- Available: Forge tier, structural drift findings (from Step 03), QMD access (Deep tier only)
- Focus: Meaning-level changes that complement structural diff
- Limits: Do not re-analyze structural changes, do not classify severity
- Dependencies: Steps 01-03 must be complete; QMD collection must exist for Deep tier

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Forge Tier

**IF forge tier is Quick, Forge, or Forge+:**

Append to {outputFile}:

```markdown
## Semantic Drift

**Status:** Skipped — Semantic diff requires Deep tier (current tier: {tier})

Semantic analysis compares QMD knowledge context for meaning-level changes that structural diff cannot detect. To enable semantic diff, run setup-forge with QMD available to unlock Deep tier.
```

Update frontmatter: append `'step-04-semantic-diff'` to `stepsCompleted`

"**Semantic diff skipped (requires Deep tier). Proceeding to severity classification...**"

→ Auto-proceed to {nextStepFile}

**IF forge tier is Deep:**

Continue to section 2.

### 2. Query Original Knowledge Context

Launch a subprocess (Pattern 3 — data operations) that:
1. Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`. Find the entry where `skill_name` matches `{skill_name}` AND `type` is `"extraction"`. Use the `name` field from that entry as the collection to query. If no matching entry exists, log: "No QMD extraction collection found for {skill_name}. Semantic diff skipped." → Auto-proceed to {nextStepFile}.
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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge tier checked FIRST — skip gracefully at Quick/Forge/Forge+
- Deep tier: QMD knowledge context queried and compared
- All semantic findings have T2 confidence labels
- Findings clearly distinguished from structural drift (T1)
- Skip notice includes explanation of what semantic diff provides
- Structured table format in drift report
- Frontmatter stepsCompleted updated

### ❌ SYSTEM FAILURE:

- Not checking tier before attempting QMD analysis
- Repeating structural findings from Step 03
- Missing confidence tier labels on findings
- Classifying severity in this step (severity is Step 05)
- Failing to skip gracefully at non-Deep tiers
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

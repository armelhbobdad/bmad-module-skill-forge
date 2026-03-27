---
name: 'step-03-structural-diff'
description: 'Compare original provenance map extractions against current scan to detect structural drift'

nextStepFile: './step-04-semantic-diff.md'
outputFile: '{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md'
---

# Step 3: Structural Diff

## STEP GOAL:

Compare the original provenance map extractions from create-skill against the current re-index snapshot from Step 02 to detect structural drift. Identify added, removed, and changed exports with file:line citations and confidence tier labels.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor performing structural comparison
- ✅ Every drift finding must have a file:line citation from either the provenance map or current scan
- ✅ Zero hallucination — only report drift that is structurally verifiable

### Step-Specific Rules:

- 🎯 Focus only on structural comparison — added/removed/changed exports
- 🚫 FORBIDDEN to classify severity — that happens in Step 05
- 🚫 FORBIDDEN to suggest remediation — that happens in Step 06
- 💬 Use subprocess Pattern 4 (parallel): In Claude Code, use multiple parallel Agent tool calls or `run_in_background: true`. In Cursor, use parallel requests (IDE-dependent). In CLI, use `xargs -P` or background processes. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- ⚙️ If subprocess unavailable, compare categories sequentially in main thread

## EXECUTION PROTOCOLS:

- 🎯 Compare provenance map exports against current extraction snapshot
- 💾 Append ## Structural Drift section to {outputFile}
- 📖 Update {outputFile} frontmatter stepsCompleted when complete
- 🚫 Only structural findings — no semantic or severity analysis

## CONTEXT BOUNDARIES:

- Available: Provenance map (from Step 01), current extraction snapshot (from Step 02), forge tier
- Focus: Structural export-level comparison only
- Limits: Do not classify severity, do not analyze semantics, do not suggest fixes
- Dependencies: Steps 01 and 02 must be complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Prepare Comparison Sets

Load both datasets:

**Baseline (from provenance map):**
- Export list with names, types, signatures, file paths, line numbers

**Current (from Step 02 extraction):**
- Export list with names, types, signatures, file paths, line numbers

Normalize both sets for comparison:
- Match by export name (primary key)
- Group by file for location-aware comparison

### 2. Detect Added Exports

**Launch subprocess (Pattern 4 — parallel execution):** In Claude Code, use multiple parallel Agent tool calls. In CLI, use `xargs -P` or equivalent.

Find exports that exist in current scan but NOT in provenance map.

For each added export, record:
- Export name, type, signature
- File path and line number (from current scan)
- Confidence tier (T1 if AST-backed, T1-low if text-based)

**If subprocess unavailable:** Iterate current exports, check against provenance map set.

### 3. Detect Removed Exports

Find exports that exist in provenance map but NOT in current scan.

For each removed export, record:
- Export name, type, signature (from provenance map)
- Original file path and line number
- Confidence tier (T1 if AST-backed, T1-low if text-based)

**Special check:** If export name exists but in a different file, classify as MOVED (not removed).

### 4. Detect Changed Exports

Find exports that exist in BOTH sets but have differences.

Compare:
- **Signature changes:** Parameter count, parameter types, return type
- **Type changes:** Function became class, const became function, etc.
- **Location changes:** Same name/signature but different file or line number (MOVED)

For each changed export, record:
- Export name
- Original signature → Current signature
- Original location → Current location
- What changed (signature / type / location)
- Confidence tier

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

For each entry in `file_entries`:
1. Locate the source file at the original `source_file` path
2. Compute current SHA-256 content hash
3. Compare against stored `content_hash`
- CHANGED: hash mismatch → record as script/asset content drift
- MISSING: source file no longer exists → record as removed
- NEW: source contains files matching script/asset patterns not in `file_entries` → record as added

Append results to the Structural Drift section as "### Script/Asset Drift ({count})".

### 5. Compile Structural Drift Section

Append to {outputFile}:

```markdown
## Structural Drift

**Comparison:** Provenance map ({provenance_date}) vs Current scan ({scan_date})
**Method:** {Quick: text-diff / Forge: AST structural / Deep: AST structural}

### Added Exports ({count})

| Export | Type | Signature | Location | Confidence |
|--------|------|-----------|----------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Removed Exports ({count})

| Export | Type | Original Signature | Original Location | Confidence |
|--------|------|-------------------|-------------------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Changed Exports ({count})

| Export | Change Type | Before | After | Location | Confidence |
|--------|------------|--------|-------|----------|------------|
| {name} | {signature/type/location} | {old} | {new} | {file}:{line} | {T1/T1-low} |

### Summary

| Category | Count |
|----------|-------|
| Added | {added_count} |
| Removed | {removed_count} |
| Changed | {changed_count} |
| **Total Drift Items** | {total} |
```

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'step-03-structural-diff'` to `stepsCompleted`

### 7. Present MENU OPTIONS

Display: "**Structural diff complete. {total} drift items found. Proceeding to semantic diff...**"

#### Menu Handling Logic:

- After structural diff section is appended and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after completion

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Structural Drift section has been appended to {outputFile} with all findings documented will you then load and read fully `{nextStepFile}` to execute and begin semantic diff analysis.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All three categories compared: added, removed, changed
- Every finding has file:line citation
- Confidence tier labels on all findings
- Moved exports distinguished from removed+added
- Structured table format in drift report
- Summary counts accurate
- Frontmatter stepsCompleted updated

### ❌ SYSTEM FAILURE:

- Missing any comparison category (added/removed/changed)
- Findings without file:line citations
- Missing confidence tier labels
- Classifying severity in this step (severity is Step 05)
- Not detecting moved exports (false removed + false added)
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

---
nextStepFile: './step-06-report.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
severityRulesFile: 'references/severity-rules.md'
---

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 by severity level (CRITICAL/HIGH/MEDIUM/LOW) using the classification rules. Calculate the overall drift score and produce a categorized findings table with confidence tier labels.

## Rules

- Only classify severity of existing findings — do not discover new drift items or suggest remediation
- Classification must be deterministic — apply {severityRulesFile} rules strictly
- Use subprocess Pattern 3 when available; if unavailable, load rules and classify in main thread

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Severity Rules

Launch a subprocess (Pattern 3 — data operations) that:
1. Loads {severityRulesFile}
2. Extracts classification criteria for each severity level
3. Returns structured rules to parent

**If subprocess unavailable:** Load {severityRulesFile} directly in main thread.

**Rules summary:**
- **CRITICAL:** Removed/renamed exports, changed signatures (breaking changes)
- **HIGH:** New public API not in skill (>3), removed helpers used in patterns, deprecated APIs
- **MEDIUM:** Implementation changes behind stable API, 1-3 new exports, moved functions
- **LOW:** Style/convention changes, comments, whitespace, internal functions

### 2. Collect All Findings

Gather all drift items from the report:

**From ## Structural Drift (Step 03):**
- Added exports
- Removed exports
- Changed exports

**From ## Semantic Drift (Step 04, if Deep tier):**
- New patterns
- Changed conventions
- Dependency shifts
- Deprecated patterns

Count total findings to classify.

### 3. Apply Severity Classification

For EACH finding, apply the severity rules:

**Structural findings classification:**
- Removed export → CRITICAL (breaking: skill references something that no longer exists)
- Changed signature → CRITICAL (breaking: skill documents wrong parameters/return type)
- Renamed export → CRITICAL (breaking: skill references old name)
- Moved export (same signature) → MEDIUM (non-breaking but location in skill is wrong)
- Added export (>3 total) → HIGH (significant API surface not documented)
- Added export (1-3 total) → MEDIUM (minor gap in coverage)

**Semantic findings classification:**
- Deprecated pattern still in skill → HIGH (skill teaches outdated approach)
- Changed convention → MEDIUM (skill may use old style)
- New pattern detected → MEDIUM (skill doesn't cover new approach)
- Dependency shift → MEDIUM (skill may reference wrong dependencies)

Record for each finding: original finding + assigned severity level.

### 4. Calculate Overall Drift Score

Apply scoring rules from {severityRulesFile}:

| Score | Criteria |
|-------|----------|
| **CLEAN** | 0 findings at any level |
| **MINOR** | LOW findings only, no MEDIUM+ |
| **SIGNIFICANT** | Any MEDIUM or HIGH findings, no CRITICAL |
| **CRITICAL** | Any CRITICAL findings present |

### 5. Compile Severity Classification Section

**Rollup inherits from step-03.** If step-03 §5 collapsed ≥ 10 same-kind findings into a single rollup row (deleted source file, renamed module, entire package tree removed), carry that rollup through to the matching severity table as one row — do not re-expand it here. Keep the existing 6-column severity table shape; the rollup encodes root cause, count, and representative symbols **inline in the `Finding` cell** rather than adding new columns, so rollup and per-item rows render cleanly in one table. Changed-signature and cross-file findings remain per-row; they were not eligible for rollup in step-03 and are not eligible here.

**Rollup row form (any severity table):**

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| N | {root cause} (×{Count}; rep: `{sym1}`, `{sym2}`, `{sym3}`, …) | {structural/semantic} | {shared detail} | {root-cause path} | {T1/T2} |

Append to {outputFile}:

```markdown
## Severity Classification

**Overall Drift Score: {CLEAN / MINOR / SIGNIFICANT / CRITICAL}**

### CRITICAL ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### HIGH ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### MEDIUM ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### LOW ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### Classification Summary

| Severity | Count | Source |
|----------|-------|--------|
| CRITICAL | {count} | {structural: N, semantic: N} |
| HIGH | {count} | {structural: N, semantic: N} |
| MEDIUM | {count} | {structural: N, semantic: N} |
| LOW | {count} | {structural: N, semantic: N} |
| **Total** | {total} | |
```

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'step-05-severity-classify'` to `stepsCompleted`
- Set `drift_score` to calculated overall score

### 7. Present MENU OPTIONS

Display: "**Severity classification complete. Overall drift score: {score}. Proceeding to report generation...**"

#### Menu Handling Logic:

- After severity classification section is appended and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after completion

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Severity Classification section has been appended to {outputFile} with all findings classified will you then load and read fully `{nextStepFile}` to execute and begin final report generation.


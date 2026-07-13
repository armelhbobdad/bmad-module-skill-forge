---
nextStepFile: 'step-doc-drift.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
severityRulesFile: '{severityRulesPath}'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 by severity level (CRITICAL/HIGH/MEDIUM/LOW) using the classification rules. Calculate the overall drift score and produce a categorized findings table with confidence tier labels.

## Rules

- Only classify severity of existing findings — do not discover new drift items or suggest remediation
- Classification must be deterministic — apply {severityRulesFile} rules strictly
- Use subprocess Pattern 3 when available; if unavailable, load rules and classify in main thread

## MANDATORY SEQUENCE

### 1. Load Severity Rules

Launch a subprocess (Pattern 3 — data operations) that:
1. Loads {severityRulesFile}
2. Extracts classification criteria for each severity level
3. Returns structured rules to parent

**If subprocess unavailable:** Load {severityRulesFile} directly in main thread.

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

For EACH finding collected in §2 (structural, and — in Deep tier — semantic), assign a severity level (CRITICAL/HIGH/MEDIUM/LOW) by matching it against the criteria in the loaded {severityRulesFile}. Record for each finding: the original finding plus its assigned severity level.

### 4. Calculate Overall Drift Score

Apply the Overall Drift Score criteria from {severityRulesFile} to the classified findings to derive the single overall score (CLEAN / MINOR / SIGNIFICANT / CRITICAL).

### 5. Compile Severity Classification Section

**Rollup inherits from step 3.** If step 3 §5 collapsed ≥ 10 same-kind findings into a single rollup row (deleted source file, renamed module, entire package tree removed), carry that rollup through to the matching severity table as one row — do not re-expand it here. Keep the existing 6-column severity table shape; the rollup encodes root cause, count, and representative symbols **inline in the `Finding` cell** rather than adding new columns, so rollup and per-item rows render cleanly in one table. Changed-signature and cross-file findings remain per-row; they were not eligible for rollup in step 3 and are not eligible here.

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
- Append `'severity-classify'` to `stepsCompleted`
- Set `drift_score` to calculated overall score

This is an auto-proceed step with no user choice: once the ## Severity Classification section has been appended with all findings classified, load, read fully, and execute `{nextStepFile}` (report generation).


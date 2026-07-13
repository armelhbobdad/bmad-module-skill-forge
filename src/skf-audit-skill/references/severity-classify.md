---
nextStepFile: 'step-doc-drift.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
severityRulesFile: '{severityRulesPath}'
severityClassifyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-severity-classify.py'
  - '{project-root}/src/shared/scripts/skf-severity-classify.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 by severity (CRITICAL/HIGH/MEDIUM/LOW), derive the overall drift score, and produce a categorized findings table with confidence-tier labels.

## Rules

- Only classify existing findings — do not discover new drift items or suggest remediation
- Reading each change and assigning its `type` / `category` is judgment; mapping those to a severity, reducing the set to the drift score, and counting per level are deterministic and delegated to the shared helper so the classification cannot drift from {severityRulesFile} between runs
- The confidence tier (T1 / T1-low / T2) travels with each finding from Steps 03/04 — the helper never touches it

## MANDATORY SEQUENCE

### 1. Collect and Categorize Findings

Gather every drift item already recorded in the report:

**From ## Structural Drift (Step 03):** added, removed, changed, and moved exports (plus any Script/Asset Drift rows).
**From ## Semantic Drift (Step 04, Deep tier only):** new patterns, changed conventions, dependency shifts, deprecated patterns.

For each finding, read {severityRulesFile} and assign the two interpretive fields the rules key on — this is the judgment step, where the nuance of the change lives:

- `type`: `removed` / `added` / `changed` / `moved` / `renamed` / `deprecated` / `semantic`
- `category`: what the change is about — e.g. `export`, `module`, `class`, `interface`, `signature`, `parameter_count`, `return_type`, `inheritance`, `internal_helper`, `default_value`, `required_parameter`, `implementation`, `optional_parameter`, `function` (for a move), or a LOW bucket (`style`, `convention`, `comment`, `documentation`, `whitespace`, `test`, `private`, `internal`). The category carries the interpretation: a removed helper referenced in a documented pattern is `internal_helper` (→ HIGH); a new private function is `private` (→ LOW).

Build one JSON array of `{type, category, detail, confidence, file, line}` objects — carry each finding's `confidence`, `file`, `line`, and human `detail` through untouched.

### 2. Classify, Score, and Count (deterministic)

Mapping type/category to a severity, reducing the severities to an overall drift score, and counting per level each have exactly one correct answer for a given finding set — delegate them to the shared helper, which encodes {severityRulesFile} directly.

**Resolve `{severityClassifyHelper}`** from `{severityClassifyProbeOrder}`; first existing path wins.

Pipe the findings array from §1 to the helper on stdin:

```bash
echo '{findings_json}' | uv run {severityClassifyHelper} -
```

Parse the emitted JSON:

```json
{
  "status": "ok",
  "drift_score": "CLEAN|MINOR|SIGNIFICANT|CRITICAL",
  "total_findings": N,
  "by_severity": {"CRITICAL": N, "HIGH": N, "MEDIUM": N, "LOW": N},
  "findings": [ {"type": "...", "category": "...", "detail": "...", "confidence": "...", "severity": "CRITICAL|HIGH|MEDIUM|LOW"} ]
}
```

Consume `by_severity`, `drift_score`, and each finding's assigned `severity` directly — do not recount or recompute the score in prose.

**If `uv`/the helper cannot execute** (e.g. claude.ai web): fall back to classifying in the main thread — apply {severityRulesFile}'s severity levels to each finding's type/category, then reduce with its Overall Drift Score table (CLEAN = no findings; MINOR = LOW only; SIGNIFICANT = any MEDIUM/HIGH, no CRITICAL; CRITICAL = any CRITICAL present).

### 3. Compile Severity Classification Section

**Rollup inherits from step 3.** If step 3 §5 collapsed ≥ 10 same-kind findings into a single rollup row (deleted source file, renamed module, entire package tree removed), carry that rollup through to the matching severity table as one row — do not re-expand it here. Keep the 6-column severity table shape; the rollup encodes root cause, count, and representative symbols **inline in the `Finding` cell** rather than adding columns, so rollup and per-item rows render cleanly in one table. Changed-signature and cross-file findings remain per-row; they were not eligible for rollup in step 3 and are not eligible here.

**Rollup row form (any severity table):**

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| N | {root cause} (×{Count}; rep: `{sym1}`, `{sym2}`, `{sym3}`, …) | {structural/semantic} | {shared detail} | {root-cause path} | {T1/T2} |

Append to {outputFile}, filling the counts from `by_severity` and each finding's assigned `severity`:

```markdown
## Severity Classification

**Overall Drift Score: {drift_score}**

### CRITICAL ({by_severity.CRITICAL})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### HIGH ({by_severity.HIGH})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### MEDIUM ({by_severity.MEDIUM})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### LOW ({by_severity.LOW})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### Classification Summary

| Severity | Count |
|----------|-------|
| CRITICAL | {by_severity.CRITICAL} |
| HIGH | {by_severity.HIGH} |
| MEDIUM | {by_severity.MEDIUM} |
| LOW | {by_severity.LOW} |
| **Total** | {total_findings} |
```

### 4. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'severity-classify'` to `stepsCompleted`
- Set `drift_score` to `{drift_score}` from the helper

Once the ## Severity Classification section has been appended with all findings classified, load, read fully, and execute `{nextStepFile}` (documentation drift).

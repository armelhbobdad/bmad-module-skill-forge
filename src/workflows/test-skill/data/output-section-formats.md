# Output Section Formats

## Coherence Analysis — Naive Mode

```markdown
## Coherence Analysis

**Mode:** Naive (structural validation only)
**Coherence category:** Not scored (weight redistributed)

### Structural Findings

| # | Type | Detail | Line |
|---|------|--------|------|
| {per-issue rows} |

**Structural Issues:** {count}
```

## Coherence Analysis — Naive Mode: Reference Consistency (split-body)

Only rendered when `references/` directory exists alongside SKILL.md.

```markdown
### Reference Consistency (split-body)

| # | Reference File | Export | Issue | SKILL.md Line | Reference Line |
|---|---------------|--------|-------|---------------|---------------|
| {per-mismatch rows} |

**Exports Cross-Checked:** {count}
**Mismatches Found:** {count}
```

## Coherence Analysis — Contextual Mode

```markdown
## Coherence Analysis

**Mode:** Contextual (full reference validation)
**References Found:** {count}
**References Valid:** {count}
**Broken References:** {count}

### Reference Validation

| Reference | Type | Line | Target Exists | Accurate | Issues |
|-----------|------|------|--------------|----------|--------|
| {per-reference rows} |

### Integration Pattern Completeness

| Pattern | Complete | Issue |
|---------|----------|-------|
| {per-pattern rows} |

### Coherence Score

- **Reference Validity:** {valid}/{total} ({percentage}%)
- **Integration Completeness:** {complete}/{total} ({percentage}%)
- **Combined Coherence:** {percentage}%
```

## Gap Report Section

```markdown
## Gap Report

**Total Gaps:** {N}
**Blocking (Critical + High):** {N}
**Non-blocking (Medium + Low + Info):** {N}

### Remediation Summary

| Severity | Count | Estimated Effort |
|----------|-------|-----------------|
| Critical | {N} | {description} |
| High | {N} | {description} |
| Medium | {N} | {description} |
| Low | {N} | {description} |
| Info | {N} | {description} |
| **Total** | **{N}** | |
```

## Gap Entry Format

```markdown
### GAP-{NNN}: {Brief title}

**Severity:** {Critical|High|Medium|Low|Info}
**Category:** {Coverage|Coherence|Structural}
**Source:** {file:line or section reference}

**Issue:** {Precise description of what is wrong or missing}

**Remediation:** {Exact action to fix this gap}
```

## Remediation Quality Rules

- **Good:** "Add documentation for `formatDate(date: Date, format?: string): string` exported from `src/utils.ts:42`. Include the optional `format` parameter with default value `'YYYY-MM-DD'`."
- **Bad:** "Document the missing function."
- **Good:** "Update signature in SKILL.md line 78 from `(date: Date) => string` to `(date: Date, format?: string) => string` to match source at `src/utils.ts:42`."
- **Bad:** "Fix the signature mismatch."

## Effort Estimation Guidelines

- Critical/High gaps: typically require reading source code and writing documentation
- Medium gaps: typically require adding type definitions or interface docs
- Low gaps: typically require adding examples or metadata
- Info: optional improvements, no action required

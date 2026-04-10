---
nextStepFile: './step-06-write.md'
---

# Step 5: Validate

## STEP GOAL:

Validate the merged skill content against the agentskills.io specification, verify all [MANUAL] sections survived the merge intact, and check confidence tier consistency across all re-extracted content. This is an advisory validation — findings are warnings, not blockers.

## Rules

- Focus only on validation — do not fix issues (that's the user's choice)
- Validation is read-only — do not modify merged content
- Use parallel validation checks (Pattern 4) when available; if unavailable, check sequentially

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Tool Availability and Validation Timing

Run: `npx skill-check -h`

- If succeeds: skill-check is available for Checks A, E, F below
- If fails: Use manual fallback paths in those checks

**Important:** Do not assume availability — empirical check required.

**Validation timing note:** Step-04 section 6b has already written SKILL.md (and stack reference files) to disk. External-tool checks against written files (skill-check Checks A, E, F) still run in **step-06 section 7** to co-locate external-tool validation with post-write verification. Structural checks (B, C, D) run here against the merged content — content on disk is byte-identical to the in-context copy.

### 2. Launch Parallel Validation Checks

Launch subprocesses in parallel for each validation category, aggregating results when complete:

**Check A — Spec Compliance (deferred to post-write):**

Skill-check requires written files on disk. This check is deferred to step-06 section 7. Perform manual structural check only: verify merged SKILL.md has required sections (exports, usage patterns, conventions), verify export entries have name/type/signature/file:line reference, flag missing sections.

**Check B — [MANUAL] Section Integrity:**
- Compare [MANUAL] inventory from step 01 against merged content
- Verify every [MANUAL] block exists in merged result, byte-identical (zero modification)
- Flag any [MANUAL] blocks moved, truncated, or missing

**Check C — Confidence Tier Consistency:**
- Verify all re-extracted exports have confidence labels (T1/T1-low/T2)
- Verify tier labels match forge tier: Quick=T1-low only, Forge=T1 (T1-low for degraded), Forge+=T1 (same as Forge, CCC improves coverage not confidence), Deep=T1+T2
- Flag mismatched or missing tier labels

**Check D — Provenance Completeness:**
- Verify every export has a provenance map entry with valid file:line references
- Verify no stale references to old file paths or line numbers
- Flag orphaned provenance entries (export removed but provenance remains)

**Check E — Diff Comparison (via skill-check):**

**If available** and previous skill version exists: `npx skill-check diff <original-skill-dir> <updated-skill-dir>`

Shows diagnostic changes between original and updated skill. Record diff results as informational context.

**If unavailable or no previous version:** Skip with note.

**Check F — Security Scan:**

**If available**, run: `npx skill-check check <skill-dir> --format json` (security scan enabled by default).

Record security findings as advisory warnings — they do not block the update.

**If unavailable:** Skip with note: "Security scan skipped — skill-check tool unavailable"

### 3. Aggregate Validation Results

Compile results from all checks:

```
Validation Results:
  spec_compliance: {status: PASS|WARN|FAIL, findings: [{severity, description, location}]}
  manual_integrity: {status, sections_verified, sections_intact, findings}
  confidence_consistency: {status, exports_checked, findings}
  provenance_completeness: {status, entries_checked, findings}
  diff_comparison: {status: PASS|SKIP, new_issues, fixed_issues, unchanged}
  security_scan: {status: PASS|WARN|SKIP, findings}
  quality_score: [0-100]  # from skill-check, if available
```

### 4. For Stack Skills — Validate Reference Files

**ONLY if skill_type == "stack":**

Repeat checks A-D for each reference file:
- `references/{library}.md` — spec compliance and [MANUAL] integrity
- `references/integrations/{pair}.md` — spec compliance and [MANUAL] integrity

**If skill_type != "stack":** Skip with notice.

### 5. Display Validation Summary

"**Validation Results:**

| Check | Status | Findings |
|-------|--------|----------|
| Spec Compliance | {PASS/WARN/FAIL} | {count} findings (quality score: {score}/100) |
| [MANUAL] Integrity | {PASS/WARN/FAIL} | {count} findings |
| Confidence Tiers | {PASS/WARN/FAIL} | {count} findings |
| Provenance | {PASS/WARN/FAIL} | {count} findings |
| Diff Comparison | {PASS/SKIP} | {new} new, {fixed} fixed |
| Security Scan | {PASS/WARN/SKIP} | {count} findings |

**Overall: {ALL_PASS / WARNINGS_FOUND / FAILURES_FOUND}**"

**If findings exist:** List each with severity, description, and location. Add: "Validation is advisory. Findings do not block the update."

### 6. Present MENU OPTIONS

Display: "**Proceeding to write updated files...**"

After validation summary is displayed, immediately load, read entire file, then execute {nextStepFile}. This is an auto-proceed step — validation is advisory, not blocking.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all validation checks have completed and findings are displayed will you load {nextStepFile} to write the updated files. Validation does NOT block — it informs.


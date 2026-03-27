---
name: 'step-05-validate'
description: 'Validate updated skill against spec, verify MANUAL integrity, and check confidence tier consistency'

nextStepFile: './step-06-write.md'
---

# Step 5: Validate

## STEP GOAL:

Validate the merged skill content against the agentskills.io specification, verify all [MANUAL] sections survived the merge intact, and check confidence tier consistency across all re-extracted content. This is an advisory validation — findings are warnings, not blockers.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a precision code analyst operating in Surgeon mode
- ✅ Validation is advisory — flag issues but do not block the workflow
- ✅ Every finding must include specific file:line reference
- ✅ Zero-hallucination principle applies to validation findings too

### Step-Specific Rules:

- 🎯 Focus ONLY on validation — do not fix issues (that's the user's choice)
- 🚫 FORBIDDEN to modify merged content — validation is read-only
- 💬 Launch parallel validation checks when subprocess available (Pattern 4): In Claude Code, use multiple parallel Agent tool calls. In Cursor, use parallel requests (IDE-dependent). In CLI, use `xargs -P`. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- ⚙️ If subprocess unavailable, perform checks sequentially in main thread

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Compile validation findings with severity levels
- 📖 Track pass/fail for each validation category
- 🚫 Validation is ADVISORY — do not block on warnings

## CONTEXT BOUNDARIES:

- Available: merged skill content from step 04, extraction results from step 03, [MANUAL] inventory from step 01
- Focus: quality assurance — spec compliance, [MANUAL] integrity, confidence consistency
- Limits: read-only — do not modify merged content
- Dependencies: step 04 must have completed merge (with or without conflict resolution)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Tool Availability and Validation Timing

Run: `npx skill-check -h`

- If succeeds: skill-check is available for Checks A, E, F below
- If fails: Use manual fallback paths in those checks

**Important:** Do not assume availability — empirical check required.

**Validation timing note:** Step-04 produces an edit plan, not written files. Checks that require files on disk (skill-check Checks A, E, F) will be **deferred to post-write** — step-06 runs them after writing files. Structural checks (B, C, D) validate the planned merge content and run here.

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All six checks executed (spec-manual, [MANUAL], confidence, provenance, diff, security)
- Checks A (spec compliance via skill-check), E (diff), and F (security scan) deferred to post-write in step-06
- Manual structural check performed for spec compliance in this step
- Stack skill reference files validated if applicable
- Findings reported with severity and specific locations; [MANUAL] integrity verified
- Auto-proceeds regardless of findings (advisory mode)

### ❌ SYSTEM FAILURE:

- Skipping any of the six checks; blocking on validation warnings
- Not verifying [MANUAL] integrity; hallucinating findings not backed by comparison
- Modifying merged content during validation (validation is read-only in this step)
- Not recording quality score when skill-check is available

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

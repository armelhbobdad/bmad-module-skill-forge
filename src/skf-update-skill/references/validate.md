---
nextStepFile: 'write.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. Check B uses its `manual-verify` subcommand to verify the
# merged (on-disk) SKILL.md against the byte-exact [MANUAL] inventory captured
# in step 1 §5 — the deterministic replacement for the LLM byte-identity
# eyeball, which could silently pass a subtly truncated block.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Validate

## STEP GOAL:

Validate the merged skill content against the agentskills.io specification, verify all [MANUAL] sections survived the merge intact, and check confidence tier consistency across all re-extracted content. This is an advisory validation — findings are warnings, not blockers.

## Rules

- Focus only on validation — do not fix issues (that's the user's choice)
- Validation is read-only — do not modify merged content
- Run the two live structural checks (B, then C) in order; Checks A, D, E, F are deferred to step 6

## Steps

### 1. Check Tool Availability and Validation Timing

Run: `npx skill-check -h`

- If succeeds: skill-check is available for Checks A, E, F below
- If fails: Use manual fallback paths in those checks

**Important:** Do not assume availability — empirical check required.

**Validation timing note:** Step-04 section 6b has already written SKILL.md to disk. External-tool checks against written files (skill-check Checks A, E, F) still run in **step 6 section 7** to co-locate external-tool validation with post-write verification. Check D (Provenance Completeness) is deterministic but needs both `metadata.json` and `provenance-map.json` on disk — neither exists yet at this step — so it is deferred to **step 6 section 6a**, which runs it via the completeness helper against the freshly-written artifacts. Structural checks (B, C) run here against the merged content — content on disk is byte-identical to the in-context copy.

### 2. Run Validation Checks

Per the §1 timing note, only Check B (a single deterministic `manual-verify` script) and Check C (an in-prompt tier-label consistency check) run live at this step; Checks A, D, E, F are deferred to step 6. Run B then C in order — one script plus one in-prompt comparison have nothing to fan out.

**Check A — Spec Compliance (deferred to post-write):**

Skill-check requires written files on disk. This check is deferred to step 6 section 7. Perform manual structural check only: verify merged SKILL.md has required sections (exports, usage patterns, conventions), verify export entries have name/type/signature/file:line reference, flag missing sections.

**Check B — [MANUAL] Section Integrity:**

Run the deterministic [MANUAL]-integrity verifier against the step-1 §5 inventory — do not eyeball byte-identity (a subtly truncated block reads as intact to the eye):

```bash
uv run {hashContentHelper} manual-verify {skill_package}/SKILL.md \
    --inventory {manual_inventory}
```

Read the verdict JSON `{"preserved":[...], "modified":[...], "missing":[...], "moved":[...], "ok":bool}` (the on-disk SKILL.md is byte-identical to the merged in-context copy per the timing note above):
- `ok == true` → status PASS. `preserved` blocks are byte-identical in place; any `moved` blocks are byte-identical but relocated with their logical parent section (report as informational, not a finding).
- `modified` non-empty → FAIL: these blocks' byte-exact interiors changed (the truncation a marker-count/eyeball check would miss). List each by name.
- `missing` non-empty → FAIL: these blocks lost their markers entirely. List each by name.

Populate the §3 `manual_integrity` record from this verdict (`sections_verified` = inventory count, `sections_intact` = `len(preserved) + len(moved)`). This check is advisory here (findings inform, do not block); write.md §1 enforces the same `ok` verdict as a HALT gate before any derived artifact is written.

**Check C — Confidence Tier Consistency:**
- Verify all re-extracted exports have confidence labels (T1/T1-low/T2)
- Verify tier labels match forge tier: Quick=T1-low only, Forge=T1 (T1-low for degraded), Forge+=T1 (same as Forge, CCC improves coverage not confidence), Deep=T1+T2
- Flag mismatched or missing tier labels

**Check D — Provenance Completeness (deferred to post-write):**

The provenance map does not exist on disk until step 6 §3 writes it, and completeness is a deterministic set-diff (metadata `exports[]` vs provenance `entries[].export_name`) plus file:line citation resolution — not something to eyeball. This check is deferred to **step 6 section 6a**, which runs `skf-verify-provenance-completeness.py` against the just-written `metadata.json` and `provenance-map.json` and reads back `missing[]` / `orphaned[]` / `stale[]` findings. Do not attempt the set comparison here — there is no provenance map to compare against yet. The `Provenance` row in §5's summary is populated from §6a's result.

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

### 6. Route to Next Step

This step auto-proceeds — no user choices; validation is advisory and does not block, it only informs. Once all validation checks have completed and findings are displayed, display "**Proceeding to write updated files...**", then load, fully read, and execute `{nextStepFile}` to write the updated files.


---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: './step-07-health-check.md'
---

# Step 6: Generate Report

## STEP GOAL:

Finalize the drift report by completing the Audit Summary with calculated metrics, generating actionable remediation suggestions for each drift finding, and adding provenance metadata. Present the final report to the user with a next-workflow recommendation.

## Rules

- Focus on completing the report — summary, remediation, provenance
- Do not discover new drift items or reclassify severity
- Remediation suggestions must be practical: what to change, where, and why
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is NOT the terminal step

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Complete Audit Summary

Update the ## Audit Summary section at the top of {outputFile} with final calculated values:

- Fill in severity count table from Step 05 classification summary
- Set overall drift score
- Add total findings count

### 2. Generate Remediation Suggestions

For EACH classified drift finding, generate a specific remediation suggestion:

**CRITICAL findings remediation:**
- Removed export → "Remove reference to `{export_name}` from SKILL.md section {section}. Export no longer exists at `{file}:{line}`."
- Changed signature → "Update `{export_name}` signature in SKILL.md from `{old_signature}` to `{new_signature}`. See `{file}:{line}`."
- Renamed export → "Replace `{old_name}` with `{new_name}` throughout SKILL.md. Renamed at `{file}:{line}`."

**HIGH findings remediation:**
- New public API (>3) → "Add documentation for {count} new exports to SKILL.md: {export_list}. Consider running update-skill workflow."
- Deprecated API → "Mark `{export_name}` as deprecated in SKILL.md. Current replacement: `{replacement}` at `{file}:{line}`."

**MEDIUM findings remediation:**
- Moved function → "Update file reference for `{export_name}` from `{old_file}` to `{new_file}:{line}`."
- New exports (1-3) → "Consider adding `{export_names}` to SKILL.md for completeness."
- Changed convention → "Review convention documentation in SKILL.md for currency."

**LOW findings remediation:**
- Style changes → "Optional: Update style references in SKILL.md to reflect current conventions."

Append to {outputFile}:

```markdown
## Remediation Suggestions

### Priority Actions (CRITICAL + HIGH)

| # | Severity | Finding | Remediation | Effort |
|---|----------|---------|-------------|--------|
| 1 | {severity} | {finding} | {specific action} | {low/medium/high} |

### Recommended Updates (MEDIUM)

| # | Finding | Remediation | Effort |
|---|---------|-------------|--------|
| 1 | {finding} | {specific action} | {low/medium} |

### Optional Improvements (LOW)

| # | Finding | Remediation |
|---|---------|-------------|
| 1 | {finding} | {specific action} |

### Workflow Recommendation

{IF any CRITICAL or HIGH findings:}
**Recommended:** Run `[US] Update Skill` workflow to apply priority remediations automatically.

{IF `audit_ref != baseline_ref` (source version bump detected in step-01 §5b):}
**Version preservation (non-destructive).** `update-skill` preserves the prior version at `{skill_group}/{baseline_version}/` unchanged and writes the new skill to `{skill_group}/{audit_version}/` (see `skf-update-skill/steps-c/step-04-merge.md` §6b, which creates the new version directory and leaves the previous one on disk). The `active` symlink at `{skill_group}/active` repoints to the new version (see `skf-update-skill/steps-c/step-06-write.md` §5b). On the next export, the prior version's export-manifest entry transitions to `status: archived` — files retained for rollback (see `skf-export-skill/steps-c/step-04-update-context.md`). Do **not** recommend `skf-drop-skill` + `skf-create-skill` for a version bump — that destroys the prior version's artifacts.

**Surface new entry points for the brief gate.** If the audit observed new top-level modules, renamed package trees, or new public entry points (new `__init__.py`, `index.ts`, `lib.rs`, or equivalent) that were not in the brief's original scope, call them out here. `update-skill` step-02 §1b detects new candidate files via heuristic and prompts `[P]romote` / `[S]kip` / `[U]pdate-brief`; surfacing them in advance makes that gate faster to resolve, or lets the user refine scope via `skf-brief-skill` before running update-skill.

{IF only MEDIUM or LOW findings:}
**Optional:** Minor drift detected. Manual updates sufficient, or run `[US] Update Skill` for automated remediation.

{IF CLEAN:}
**No action needed.** Skill is current with source code.
```

### 3. Add Provenance Section

Append to {outputFile}:

```markdown
## Provenance

| Field | Value |
|-------|-------|
| **Audit Date** | {current_date} |
| **Audited By** | Ferris (Audit mode) |
| **Forge Tier** | {tier} |
| **Tools Used** | {tool_list based on tier} |
| **Source Path** | {source_path} |
| **Skill Path** | {skill_path} |
| **Provenance Map** | {provenance_map_path} |
| **Provenance Age** | {days} days |
| **Mode** | {normal / degraded} |
| **Baseline Ref / Commit** | `{baseline_ref}` @ `{baseline_commit_short}` |
| **Audit Ref / Commit** | `{audit_ref}` @ `{audit_commit_short}` ({audit_ref_source}) |
| **Upstream Latest** | `{latest_tag or remote_head or "(not fetched)"}` |

**Confidence Legend:**
- **T1:** AST extraction — high reliability, structural truth
- **T1-low:** Text pattern matching — moderate reliability
- **T2:** QMD temporal context — evidence-backed semantic analysis
```

### 4. Update Report Frontmatter

Update {outputFile} frontmatter:
- Append `'step-06-report'` to `stepsCompleted`
- Set `drift_score` to final calculated score
- Set `nextWorkflow` to `'update-skill'` if CRITICAL or HIGH findings, otherwise leave empty

### 5. Present Final Report Summary

"**Audit Complete: {skill_name}**

---

**Overall Drift Score: {CLEAN / MINOR / SIGNIFICANT / CRITICAL}**

| Severity | Count |
|----------|-------|
| CRITICAL | {count} |
| HIGH | {count} |
| MEDIUM | {count} |
| LOW | {count} |
| **Total** | {total} |

**Report saved to:** `{outputFile}`

{IF CRITICAL/HIGH findings:}
**Action Required:** {count} priority items need remediation. Recommend running `[US] Update Skill` workflow.

{IF MEDIUM/LOW only:}
**Minor Drift:** Skill is functional but could benefit from updates. See report for details.

{IF CLEAN:}
**All Clear:** No drift detected. Skill accurately reflects current source code.

---

**Next Steps:**
{IF findings exist:}
1. **[US] Update Skill** — Automatically apply remediations from this drift report
2. **Review report** — Manual review at `{outputFile}`

{IF CLEAN:}
1. **No action needed** — Skill is current
2. **[EX] Export Skill** — Skill is ready for distribution

---

**Audit workflow complete.**"

### Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_version}/audit-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include the drift report path in `outputs`; include `drift_count` and `severity` (CLEAN/MINOR/SIGNIFICANT/CRITICAL) in `summary`.

### 6. Chain to Health Check

ONLY WHEN the report has been written, presented, and the result contract saved will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the user-facing summary reads as final.


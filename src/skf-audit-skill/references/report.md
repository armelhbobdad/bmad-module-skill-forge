---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Drift report prose in {document_output_language}. -->

# Step 6: Generate Report

## STEP GOAL:

Finalize the drift report by completing the Audit Summary with calculated metrics, generating actionable remediation suggestions for each drift finding, and adding provenance metadata. Present the final report to the user with a next-workflow recommendation.

## Rules

- Focus on completing the report — summary, remediation, provenance
- Do not discover new drift items or reclassify severity
- Remediation suggestions must be practical: what to change, where, and why
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is NOT the terminal step

## MANDATORY SEQUENCE

### 1. Complete Audit Summary

Update the ## Audit Summary section at the top of {outputFile} with final calculated values:

- Fill in severity count table from Step 05 classification summary
- Set overall drift score
- Add total findings count
- Include doc drift summary from `doc_drift_summary` context (set by step 5a):
  - If `changed > 0`: "**Doc Drift:** {changed} of {total_tracked} tracked doc(s) have changed since compile. Consider re-running CS to update doc_sources."
  - If `fetch_failed > 0`: "{fetch_failed} doc URL(s) could not be reached during audit."
  - If `skipped_entirely`: no mention in summary (already noted in the doc drift section)

### 2. Generate Remediation Suggestions

For each classified drift finding, write one concrete remediation derived from the finding itself: **what** to change in the audited **SKILL.md** (or its `references/`) — not the source code — **where** (the section plus the source `{file}:{line}` the finding cites), and **why**. Set effort (`low`/`medium`/`high`) by how much of the skill doc the change touches. A reviewer should be able to act on each row without re-deriving the finding.

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

{IF `audit_ref != baseline_ref` (source version bump detected in step 1 §5b):}
**Version preservation (non-destructive).** `update-skill` preserves the prior version at `{skill_group}/{baseline_version}/` unchanged and writes the new skill to `{skill_group}/{audit_version}/` (see `skf-update-skill/references/merge.md` §6b, which creates the new version directory and leaves the previous one on disk). The `active` symlink at `{skill_group}/active` repoints to the new version (see `skf-update-skill/references/write.md` §5b). On the next export, the prior version's export-manifest entry transitions to `status: archived` — files retained for rollback (see `skf-export-skill/references/update-context.md`). Do **not** recommend `skf-drop-skill` + `skf-create-skill` for a version bump — that destroys the prior version's artifacts.

**Surface new entry points for the brief gate.** If the audit observed new top-level modules, renamed package trees, or new public entry points (new `__init__.py`, `index.ts`, `lib.rs`, or equivalent) that were not in the brief's original scope, call them out here. `update-skill` step 2 §1b detects new candidate files via heuristic and prompts `[P]romote` / `[S]kip` / `[U]pdate-brief`; surfacing them in advance makes that gate faster to resolve, or lets the user refine scope via `skf-brief-skill` before running update-skill.

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
- Append `'report'` to `stepsCompleted`
- Set `drift_score` to the score from step 5's classification helper
- Set `nextWorkflow` to `'update-skill'` if CRITICAL or HIGH findings, otherwise leave empty

If finalizing the report or writing the result JSON below fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract) with `report_path: null`.

### 5. Present Final Report Summary

Present a concise completion summary to the user conveying: the skill name, the **overall drift score** (CLEAN / MINOR / SIGNIFICANT / CRITICAL), the severity-count table (CRITICAL / HIGH / MEDIUM / LOW / Total), and the saved report path (`{outputFile}`). Close with the next-action recommendation matching the drift level:

- **CRITICAL or HIGH findings** → action required: recommend running the `[US] Update Skill` workflow to apply the priority remediations; manual review at `{outputFile}` is the alternative.
- **MEDIUM or LOW only** → minor drift: manual updates suffice, or run `[US] Update Skill` for automated remediation.
- **CLEAN** → no action needed; the skill is current and ready for `[EX] Export Skill`.

This summary reads as final but is **not** the terminal step — proceed to §6.

### Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_version}/audit-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include the drift report path in `outputs`; include `drift_count` and `severity` (CLEAN/MINOR/SIGNIFICANT/CRITICAL) in `summary`.

**Stdout envelope (headless only).** When `{headless_mode}` is true, emit a single-line JSON envelope to **stdout** immediately after the on-disk result contract is written, so chaining workflows can consume `drift_score`, `report_path`, and `next_workflow` from a captured stdout line without polling the filesystem. The shape matches the "Result Contract (Headless)" section in SKILL.md verbatim:

```
SKF_AUDIT_RESULT_JSON: {"status":"success","skill_name":"{skill_name}","drift_score":"{CLEAN|MINOR|SIGNIFICANT|CRITICAL}","report_path":"{outputFile}","next_workflow":"{update-skill|null}","audit_ref":"{audit_ref}","exit_code":0,"halt_reason":null}
```

Field rules: `next_workflow` is `"update-skill"` when CRITICAL or HIGH findings exist (matches the frontmatter `nextWorkflow` set in §4), otherwise `null`. `audit_ref` carries the resolved value from step 1 §5b (`baseline_ref` when no upstream drift was detected, `latest_tag` or `remote_head` when the operator chose `[C] Checkout-and-audit-against-latest`).

**Hard-halt envelope (headless only).** Every hard halt emits this same envelope shape on **stderr** with `status: "error"` and the `exit_code` / `halt_reason` for its failure class (per SKILL.md → Exit Codes and Result Contract), produced at the halting site before exit — it is the only failure signal a wrapping pipeline receives, so log it before exiting. `drift_score` carries its last known value (`null` if classification never ran); `report_path` is `null` when the report write failed.

**Post-audit hook (optional).** If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it as:

```bash
{onCompleteCommand} --result-path={result_json_path}
```

where `{result_json_path}` is the per-run record path written above (`{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json`). Log success/failure to `workflow_warnings[]` — never fail the workflow on a hook error. The hook runs after the result contract is finalized so notifiers, ticket-tracker integrations, or downstream pipelines see a complete record. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 6. Chain to Health Check

Only when the report has been written, presented, and the result contract saved do you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the user-facing summary reads as final.


---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: 'health-check.md'
# This run's stage data folder, where step 5 saved the findings and their
# classification.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
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

- Fill in the severity count table from `{auditDataFolder}/severity.json`, the classification step 5 saved: `by_severity` for each level and `total_items` for **Total**
- Set the overall drift score (its `drift_score`)
- Include doc drift summary from `doc_drift_summary` context (set by step 5a):
  - If `changed > 0`: "**Doc Drift:** {changed} of {total_tracked} tracked doc(s) have changed since compile. Consider re-running CS to update doc_sources."
  - If `fetch_failed > 0`: "{fetch_failed} doc URL(s) could not be reached during audit."
  - If `skipped_entirely`: no mention in summary (already noted in the doc drift section)

### 2. Generate Remediation Suggestions

For each classified drift finding (`findings[]` of `{auditDataFolder}/severity.json`; one remediation may cover a rollup row of step 5's tables), write one concrete remediation derived from the finding itself: **what** to change in the audited **SKILL.md** (or its `references/`), not the source code; **where** (the section plus the source `{file}:{line}` the finding cites); and **why**. Set effort (`low`/`medium`/`high`) by how much of the skill doc the change touches. A reviewer should be able to act on each row without re-deriving the finding.

Rows of step 3's **Provenance label differences (not drift)** table are not findings: they get no remediation row and do not count toward the Workflow Recommendation.

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

{IF the frontmatter's `audit_ref_source` is `checkout-latest` (step 1 §5b audited a newer upstream ref than the baseline):}
**Version preservation (non-destructive).** `update-skill` keeps the audited version (`{audited_version}`) unchanged, writes the new version in a folder of its own beside it (see `skf-update-skill/references/merge.md` §6b, which leaves the previous version on disk) and repoints the skill's `active` link at it (see `skf-update-skill/references/write.md` §5b). On the next export, the prior version's export-manifest entry transitions to `status: archived`, its files kept for rollback (see `skf-export-skill/references/update-context.md`). Do **not** recommend `skf-drop-skill` + `skf-create-skill` for a version bump: that destroys the prior version's artifacts.

**Surface new entry points for the brief gate.** If the audit observed new top-level modules, renamed package trees, or new public entry points (new `__init__.py`, `index.ts`, `lib.rs`, or equivalent) that were not in the brief's original scope, call them out here. `update-skill` step 2 §1b detects new candidate files via heuristic and prompts `[P]romote` / `[S]kip` / `[U]pdate-brief`; surfacing them in advance makes that gate faster to resolve, or lets the user refine scope via `skf-brief-skill` before running update-skill.

{IF only MEDIUM or LOW findings:}
**Optional:** Minor drift detected. Manual updates sufficient, or run `[US] Update Skill` for automated remediation.

{IF CLEAN:}
**No action needed.** Skill is current with source code.
```

### 3. Add Provenance Section

Build the section from the frontmatter of {outputFile}, where step 1 §6, step 2 §5 and step 3 §6 recorded each value as it was known, not from values held in the conversation. Append to {outputFile}:

```markdown
## Provenance

| Field | Value |
|-------|-------|
| **Audit Date** | {date} |
| **Audited By** | Ferris (Audit mode) |
| **Forge Tier** | {forge_tier} |
| **Tools Used** | {tool_list based on forge_tier} |
| **Source Path** | {source_path} |
| **Skill Path** | {skill_path} |
| **Audited Version** | `{audited_version}` ({audited_version_reason}){; the export manifest names `{manifest_version}`, when set} |
| **Provenance Map** | {provenance_map} |
| **Provenance Age** | {provenance_age_days} days (generated {provenance_generated_at}) |
| **Mode** | {confidence_mode} |
| **AST fallback files** | {`ast_fallback_files`, or none; n/a at Quick} |
| **Applied Transforms** | {each `applied_transforms` entry as `{transform}` ×{count}, or none} |
| **Baseline Ref / Commit** | `{baseline_ref}` @ `{baseline_commit_short}` |
| **Audit Ref / Commit** | `{audit_ref}` @ `{audit_commit_short}` ({audit_ref_source}) |
| **Upstream Latest** | `{latest_tag or remote_head or "(not fetched)"}` (fetch: {upstream_fetch}) |
| **Stage Data** | `{auditDataFolder}/`: the JSON this run saved and classified (the structural diff or the constituents' freshness, the findings and their classification) |

**Confidence Legend:**
- **T1:** an ast-grep match (`extraction_method: ast-grep`) at any tier: high reliability, structural truth
- **T1-low:** read by eye (`extraction_method: source-read`) at any tier: moderate reliability
- **T1-low-fallback:** Deep-tier semantic diff read directly from the skill's docs and the current source because the QMD collection was empty: moderate reliability
- **T2:** QMD temporal context — evidence-backed semantic analysis
- **T3:** external documentation reference: variable reliability, secondary source
```

### 4. Update Report Frontmatter

Update {outputFile} frontmatter:
- Append `'report'` to `stepsCompleted`
- Set `drift_score` to the score from step 5's classification helper
- Set `nextWorkflow` to `'update-skill'` when the saved classification's `by_severity.CRITICAL` or `by_severity.HIGH` is above 0, otherwise leave it empty

If finalizing the report or writing the result JSON below fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract) with `report_path: null`.

### 5. Present Final Report Summary

Present a concise completion summary to the user conveying: the skill name, the **overall drift score** (CLEAN / MINOR / SIGNIFICANT / CRITICAL), the severity-count table (CRITICAL / HIGH / MEDIUM / LOW / Total), and the saved report path (`{outputFile}`). Close with the next-action recommendation matching the drift level:

- **CRITICAL or HIGH findings** → action required: recommend running the `[US] Update Skill` workflow to apply the priority remediations; manual review at `{outputFile}` is the alternative. When the frontmatter's `audit_ref_source` is `checkout-latest` (step 1 §5b checked out a newer ref), recommend `[US] Update Skill` with `--target-ref {latest_tag}` when its `audit_ref` is its `latest_tag`, or `--target-ref HEAD` when it is its `remote_head` (the remote default branch): update-skill otherwise compares the ref the skill is pinned to, not the one this audit read.
- **MEDIUM or LOW only** → minor drift: manual updates suffice, or run `[US] Update Skill` for automated remediation.
- **CLEAN** → no action needed; the skill is current and ready for `[EX] Export Skill`.

This summary reads as final but is **not** the terminal step — proceed to §6.

### Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_version}/audit-skill-result-latest.json` (stable path for pipeline consumers: a copy, not a symlink). Include the drift report path in `outputs`; include `drift_count` (the saved classification's `total_findings`: one per finding, never a label difference) and `severity` (its `drift_score`: CLEAN/MINOR/SIGNIFICANT/CRITICAL) in `summary`.

**Stdout envelope (headless only).** When `{headless_mode}` is true, emit a single-line JSON envelope to **stdout** immediately after the on-disk result contract is written, so chaining workflows can consume `drift_score`, `report_path`, and `next_workflow` from a captured stdout line without polling the filesystem. The shape matches the "Result Contract (Headless)" section in SKILL.md verbatim:

```
SKF_AUDIT_RESULT_JSON: {"status":"success","skill_name":"{skill_name}","drift_score":"{CLEAN|MINOR|SIGNIFICANT|CRITICAL}","report_path":"{outputFile}","next_workflow":"{update-skill|null}","audit_ref":"{audit_ref}","exit_code":0,"halt_reason":null}
```

Field rules: `next_workflow` is `"update-skill"` when CRITICAL or HIGH findings exist (matches the frontmatter `nextWorkflow` set in §4), otherwise `null`. `audit_ref` is the frontmatter's `audit_ref`, resolved at step 1 §5b (`baseline_ref` when no upstream drift was detected, `latest_tag` or `remote_head` when the operator chose `[C] Checkout-and-audit-against-latest`).

**Hard-halt envelope (headless only).** Every hard halt emits this same envelope shape on **stderr** with `status: "error"` and the `exit_code` / `halt_reason` for its failure class (per SKILL.md → Exit Codes and Result Contract), produced at the halting site before exit — it is the only failure signal a wrapping pipeline receives, so log it before exiting. `drift_score` carries its last known value (`null` if classification never ran); `report_path` is `null` when the report write failed.

**Post-audit hook (optional).** If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it as:

```bash
{onCompleteCommand} --result-path={result_json_path}
```

where `{result_json_path}` is the per-run record path written above (`{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json`). Log success/failure to `workflow_warnings[]` — never fail the workflow on a hook error. The hook runs after the result contract is finalized so notifiers, ticket-tracker integrations, or downstream pipelines see a complete record. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 6. Chain to Health Check

Only when the report has been written, presented, and the result contract saved do you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the user-facing summary reads as final.


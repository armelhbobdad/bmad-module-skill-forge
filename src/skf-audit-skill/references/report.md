---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: 'health-check.md'
# This run's stage data folder, where step 5 saved the findings and their
# classification.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
# Resolve `{sourceTreeHelper}` to the first existing path. The Result
# Contract removes the private tree step 1 §5b's [C] read the source in.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
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

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (step 1 §5b's [C]), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}", "drift_score": "<the saved classification's drift_score>"}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

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

**Public API outside the skill's scope.** When `{extractionSnapshot}` (`{forge_version}/extraction-snapshot.json`, step 2) lists items in `outside_scope`, a package entry point exports public API from files the skill does not cover: the recipe runner's entry-point diff found them, so nothing here is judged by eye. Write one table row per item, the defining file as the path and the names it exports (and the entry points that export them) as the evidence, in the `### Out-of-Scope New Public API` subsection below. update-skill's scope reconciliation (`skf-provenance-gap-dispatch.py`) reads that subsection from the newest drift report and asks whether to bring each path into scope. Leave the subsection out when `outside_scope` is empty or the snapshot has none (Quick tier, a compose-mode stack).

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

### Out-of-Scope New Public API

| Path | Evidence |
|------|----------|
| `{outside_scope[].path}` | exports `{name}`, `{name}` through `{entry point}` |

### Workflow Recommendation

{IF any CRITICAL or HIGH findings:}
**Recommended:** Run `[US] Update Skill` workflow to apply priority remediations automatically.

{IF the frontmatter's `upstream_moved` is true:}
**Upstream moved.** The skill is built from `{baseline_ref}` and upstream is now at `{upstream_ref}`{; this audit read `{upstream_ref}`, when `audit_ref_source` is `checkout-latest`; this audit read the baseline, otherwise}. Run `[US] Update Skill` with `--target-ref {upstream_ref}`, so the update compares the ref upstream moved to rather than the one the skill is pinned to.

{IF the frontmatter's `audit_ref_source` is `checkout-latest` (step 1 §5b audited a newer upstream ref than the baseline) or its `upstream_moved` is true:}
**Version preservation (non-destructive).** `update-skill` keeps the audited version (`{audited_version}`) unchanged, writes the new version in a folder of its own beside it (see `skf-update-skill/references/merge.md` §6b, which leaves the previous version on disk) and repoints the skill's `active` link at it (see `skf-update-skill/references/write.md` §5b). On the next export, the prior version's export-manifest entry transitions to `status: archived`, its files kept for rollback (see `skf-export-skill/references/update-context.md`). Do **not** recommend `skf-drop-skill` + `skf-create-skill` for a version bump: that destroys the prior version's artifacts.

{IF the Out-of-Scope New Public API table above has rows:}
**New public API outside the scope.** update-skill's scope reconciliation (detect-changes §1c) offers each path to bring into the brief's scope; review them there, or refine the scope with `skf-brief-skill` before running update-skill.

{IF only MEDIUM or LOW findings:}
**Optional:** Minor drift detected. Manual updates sufficient, or run `[US] Update Skill` for automated remediation.

{IF CLEAN:}
**No drift against `{audit_ref}`.** The skill matches the source at `{audit_ref}` (`{audit_commit_short}`){; upstream has not moved past `{baseline_ref}`, when `upstream_moved` is false; upstream was not checked ({upstream_fetch}), when it is null; and when it is true, the Upstream moved recommendation above applies}.
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
| **Source Path** | {source_path}{; read from the private tree `{source_tree}`, when set} |
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
| **Upstream Moved** | {upstream_moved}{: to `{upstream_ref}`, when true} |
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
- Set `nextWorkflow` to `'update-skill'` when the saved classification's `by_severity.CRITICAL` or `by_severity.HIGH` is above 0, or when the frontmatter's `upstream_moved` is true, otherwise leave it empty

If finalizing the report fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`, phase `report:write`, `"path": "{outputFile}"`, and no `report_path` in the payload.

### 5. Present Final Report Summary

Present a concise completion summary to the user conveying: the skill name, the **overall drift score** (CLEAN / MINOR / SIGNIFICANT / CRITICAL), the severity-count table (CRITICAL / HIGH / MEDIUM / LOW / Total), and the saved report path (`{outputFile}`). Close with the next-action recommendation matching the drift level:

- **CRITICAL or HIGH findings** → action required: recommend running the `[US] Update Skill` workflow to apply the priority remediations; manual review at `{outputFile}` is the alternative.
- **The frontmatter's `upstream_moved` is true**, whatever the drift score → recommend `[US] Update Skill` with `--target-ref {upstream_ref}`, naming `{baseline_ref}` and `{upstream_ref}`: update-skill otherwise compares the ref the skill is pinned to, not the one upstream moved to. `{upstream_ref}` is the newer tag when upstream released one (`--target-ref {latest_tag}`), and for a skill built from the default branch it is `HEAD` (`--target-ref HEAD`).
- **MEDIUM or LOW only** → minor drift: manual updates suffice, or run `[US] Update Skill` for automated remediation.
- **CLEAN, and `upstream_moved` is not true** → no action needed: the skill matches `{audit_ref}` and is ready for `[EX] Export Skill`.

This summary reads as final but is **not** the terminal step — proceed to §6.

### Result Contract

**Remove the private source tree first.** When `{source_tree}` is set (step 1 §5b's [C] read the source there), no later step reads the source: resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} close --tree "{source_tree}"`. Go on whatever it prints. On `left` or `refused`, a command that fails or prints no JSON, or no candidate, record `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "source_tree_not_removed: {source_tree}"` (a later SKF run removes it once it is seven days old). Then set `{source_tree}` to null.

The shared emitter writes the result contract (per `shared/references/output-contract-schema.md`, which resolves relative to the SKF module root: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) and prints the `SKF_AUDIT_RESULT_JSON` envelope; this step stages their content, every value from the drift report's frontmatter and the classification step 5 saved. Write `{run_dir}/result-context.json`:

```json
{
  "status": "success",
  "skill_name": "{skill_name}",
  "drift_score": "<drift_score>",
  "report_path": "{outputFile}",
  "next_workflow": "<update-skill>" | null,
  "audit_ref": "<audit_ref>",
  "upstream_moved": true | false | null,
  "upstream_ref": "<upstream_ref>" | null,
  "result_contract": {
    "skill": "skf-audit-skill",
    "status": "success",
    "outputs": [{"type": "report", "path": "{outputFile}"}],
    "summary": {"drift_count": <total_findings>, "severity": "<drift_score>", "next_workflow": "<update-skill>" | null,
                "audit_ref": "<audit_ref>", "upstream_moved": true | false | null, "upstream_ref": "<upstream_ref>" | null}
  }
}
```

When On Activation step 3 fell back to the bundled `customize.toml`, add `"customization_resolver_unavailable": "<the reason>"`: the emitter turns it into a warning. `<drift_score>` and `<total_findings>` are the `drift_score` and `total_findings` of `{auditDataFolder}/severity.json`: `drift_count` (the saved classification's `total_findings`: one per finding, never a label difference) and `severity` (its `drift_score`: CLEAN/MINOR/SIGNIFICANT/CRITICAL). `next_workflow` is `"update-skill"` exactly when §4 set the frontmatter's `nextWorkflow` (CRITICAL or HIGH findings, or `upstream_moved` true), else `null`. `audit_ref`, `upstream_moved` and `upstream_ref` are the frontmatter's, resolved at step 1 §5b (`audit_ref` is `baseline_ref` when the audit stayed on the baseline, `upstream_ref` when the operator chose `[C]`). Then run, in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-audit-skill --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

It writes `{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name) and its `audit-skill-result-latest.json` copy (stable path for pipeline consumers: a copy, not a symlink), stamps the timestamp, `run_id`, `headless_decisions` and `warnings` into both, and prints the `SKF_AUDIT_RESULT_JSON:` line on stdout. When `{headless_mode}` is true, display the line verbatim: chaining workflows read `drift_score`, `report_path`, `next_workflow`, `upstream_moved` and `upstream_ref` from it without polling the filesystem. A result file that could not be written leaves `result_path` null and a `result_file_write_failed` warning in the line, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HALT with **exit 4**, `halt_reason: "write-failed"`, phase `report:result-contract`: the run's result contract could not be written.

**Hard-halt envelope (headless only).** Every hard halt prints its envelope through the emitter on **stderr** with `status: "error"` and the `exit_code` / `halt_reason` for its failure class, as each step's **Halt envelope** paragraph shows: it is the only failure signal a wrapping pipeline receives. `drift_score` carries its last known value (`null` if classification never ran); `report_path` is `null` when the report write failed.

**Post-audit hook (optional).** If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it as:

```bash
{onCompleteCommand} --result-path={result_json_path}
```

where `{result_json_path}` is the envelope's `result_path`, the per-run record the emitter wrote (skip the hook when it is null). When the hook fails, tell the user it failed and why, and go on: never fail the workflow on a hook error. The hook runs after the result contract is finalized so notifiers, ticket-tracker integrations, or downstream pipelines see a complete record. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 6. Chain to Health Check

Only when the report has been written, presented, and the result contract saved, delete the run folder, whose decisions, warnings and payloads the run no longer needs: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step: do not stop here even though the user-facing summary reads as final.


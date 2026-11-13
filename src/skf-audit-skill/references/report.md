---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: 'health-check.md'
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
renderDriftTablesScript: 'scripts/render-drift-tables.py'
resultContextScript: 'scripts/build-result-context.py'
resolveCustomizationProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py'
  - '{project-root}/src/shared/scripts/skf-resolve-customization.py'
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
- The post-audit hook runs `{resolveCustomizationHelper}`, resolved from `{resolveCustomizationProbeOrder}` when it is not bound.
- `{compose_mode_stack}` is the `compose_mode_stack` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still skips the snapshot a compose-mode stack does not have
- `{docs_only_skill}` is the `docs_only_skill` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still skips the snapshot and words the doc drift line for a docs-only skill

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (the [C] of `upstream-checkout.md`), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}`, with `{sourceTreeHelper}` resolved from `{sourceTreeProbeOrder}` when it is not bound, and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}", "drift_score": "<the saved classification's drift_score>"}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Complete Audit Summary

Update the ## Audit Summary section at the top of {outputFile} with final calculated values:

- Fill in the severity count table from `{auditDataFolder}/severity.json`, the classification step 5 saved: `by_severity` for each level and `total_items` for **Total**
- Set the overall drift score (its `drift_score`)
- Include the doc drift counts, the `stats` of `{auditDataFolder}/doc-drift.json`, the comparison step 5a saved:
  - If `changed > 0`: "**Doc Drift:** {changed} of {total_tracked} tracked doc(s) have changed since compile." Then, for a docs-only skill (`{docs_only_skill}`, whose score these changes set): "Run `[US] Update Skill` to bring the skill up to them."; otherwise: "Consider re-running CS to update doc_sources."
  - If `fetch_failed > 0`: "{fetch_failed} doc URL(s) could not be reached during audit."
  - If the file does not exist, step 5a skipped the check: no mention in the summary (its Documentation Drift section already says why)

### 1b. Build the Result Context

Build the result payload and the route it hands on from the drift report's frontmatter and the classification step 5 saved, never by hand: `{resultContextScript}` (it resolves relative to the skill root) reads both, works out `next_workflow` and writes the payload the Result Contract hands the emitter. When On Activation step 3 kept a `{customization_resolver_unavailable}` reason, first write it to `{run_dir}/resolver-unavailable.txt` with a file write, never `echo` (the reason can hold quotes, backticks or `$( )`), and pass that file's text. From `{project-root}`, run:

```bash
uv run {resultContextScript} --report "{outputFile}" --classification "{auditDataFolder}/severity.json" [--resolver-unavailable "$(cat "{run_dir}/resolver-unavailable.txt")"] --output "{run_dir}/result-context.json"
```

Bind `{next_workflow}` ← its JSON's `next_workflow` (`update-skill`, or null). Exit 2: correct the command and run it again. On exit 1, its `error` names the value or the file it could not read: fix that value in {outputFile}'s frontmatter, or that file, and run the command once more. If it exits 1 again, HALT with **exit 4**, `halt_reason: "write-failed"`, phase `report:result-contract`: the run's result payload could not be built.

### 2. Generate Remediation Suggestions

For each classified drift finding (`findings[]` of `{auditDataFolder}/severity.json`; one remediation may cover a rollup row of step 5's tables), write one concrete remediation derived from the finding itself: **what** to change in the audited **SKILL.md** (or its `references/`), not the source code; **where** (the section plus the source `{file}:{line}` the finding cites); and **why**. Set effort (`low`/`medium`/`high`) by how much of the skill doc the change touches. A reviewer should be able to act on each row without re-deriving the finding.

Rows of step 3's **Provenance label differences (not drift)** table are not findings: they get no remediation row and do not count toward the Workflow Recommendation.

**Public API outside the skill's scope.** Step 2's snapshot lists in `outside_scope` the files the skill does not cover whose public API a package entry point exports: the recipe runner's entry-point diff found them, so nothing here is judged by eye. Render their subsection from the snapshot, never by hand. `{renderDriftTablesScript}` resolves relative to the skill root; from `{project-root}`, run:

```bash
uv run {renderDriftTablesScript} outside-scope "{forge_version}/extraction-snapshot.json"
```

Paste its output unchanged under Remediation Suggestions, where the template below shows it (nothing when it prints nothing: `outside_scope` is empty, as at Quick tier). update-skill's scope reconciliation (`skf-provenance-gap-dispatch.py`) reads that subsection from the newest finished drift report and asks whether to bring each path into scope. A compose-mode stack and a docs-only skill have no snapshot: skip the command. When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not read: write `Out-of-Scope New Public API not rendered: {error}` in place of its output and go on.

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

{what the outside-scope command printed, unchanged}

### Workflow Recommendation

{IF {next_workflow} is update-skill:}
**Recommended:** Run `[US] Update Skill`{ with `--target-ref {upstream_ref}`, when the frontmatter's `upstream_moved` is true}{ to apply the Priority Actions above, when that table has rows}.

{IF the frontmatter's `upstream_moved` is true:}
**Upstream moved.** The skill is built from `{baseline_ref}` and upstream is now at `{upstream_ref}`{; this audit read `{upstream_ref}`, when `audit_ref_source` is `checkout-latest`; this audit read the baseline, otherwise}. Run `[US] Update Skill` with `--target-ref {upstream_ref}`, so the update compares the ref upstream moved to rather than the one the skill is pinned to.

{IF the frontmatter's `audit_ref_source` is `checkout-latest` (the [C] of `upstream-checkout.md` audited a newer upstream ref than the baseline) or its `upstream_moved` is true:}
**Version preservation (non-destructive).** `update-skill` keeps the audited version (`{audited_version}`) unchanged, writes the new version in a folder of its own beside it, leaving the previous version on disk, and repoints the skill's `active` link at it. On the next export, the prior version's export-manifest entry becomes `status: archived`, its files kept for rollback. Do **not** recommend `skf-drop-skill` + `skf-create-skill` for a version bump: that destroys the prior version's artifacts.

{IF the Out-of-Scope New Public API table above has rows:}
**New public API outside the scope.** update-skill's scope reconciliation offers each path to bring into the brief's scope; review them there, or refine the scope with `skf-brief-skill` before running update-skill.

{IF only MEDIUM or LOW findings, and {next_workflow} is null:}
**Optional:** Minor drift detected. Manual updates sufficient, or run `[US] Update Skill` for automated remediation.

{IF CLEAN:}
**No drift against `{audit_ref}`.** The skill matches the source at `{audit_ref}` (`{audit_commit_short}`){; upstream has not moved past `{baseline_ref}`, when `upstream_moved` is false; upstream was not checked ({upstream_fetch}), when it is null; and when it is true, the Upstream moved recommendation above applies}.{ The skill is ready for `[EX] Export Skill`, when `upstream_moved` is not true.}
```

### 3. Add Provenance Section

Render the section's table from the frontmatter of {outputFile}, where step 1 §6, step 2 §5 and step 3 §6 recorded each value as it was known, never from values held in the conversation or by hand. From `{project-root}`, run:

```bash
uv run {renderDriftTablesScript} provenance "{outputFile}" --stage-data "{auditDataFolder}"
```

It prints the Field and Value table (`--help` lists its rows). Append to {outputFile}:

```markdown
## Provenance

{what the provenance command printed, unchanged}

**Confidence Legend:**
- **T1:** an ast-grep match (`extraction_method: ast-grep`) at any tier: high reliability, structural truth
- **T1-low:** read by eye (`extraction_method: source-read`) at any tier: moderate reliability
- **T1-low-fallback:** Deep-tier semantic diff read directly from the skill's docs and the current source because no QMD extraction collection was registered for the skill, or the one registered was empty: moderate reliability
- **T2:** Deep-tier semantic diff: a claim the skill's QMD collection holds, checked against the current source line it cites: evidence-backed semantic analysis
- **T3:** external documentation reference: variable reliability, secondary source
```

When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not read: write `Provenance table not rendered: {error}` in place of its output and go on.

### 4. Update Report Frontmatter

Update {outputFile} frontmatter:
- Append `'report'` to `stepsCompleted`
- Set `drift_score` to the score from step 5's classification helper
- Set `nextWorkflow` to `{next_workflow}`, the route §1b bound (empty when it is null)

If finalizing the report fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`, phase `report:write`, `"path": "{outputFile}"`, and no `report_path` in the payload.

### 5. Present Final Report Summary

Present a concise completion summary to the user conveying: the skill name, the **overall drift score** (CLEAN / MINOR / SIGNIFICANT / CRITICAL), the severity-count table (CRITICAL / HIGH / MEDIUM / LOW / Total), and the saved report path (`{outputFile}`). Close with the recommendation §2's Workflow Recommendation chose: each block it wrote, read from `{outputFile}`.

This summary reads as final but is **not** the terminal step — proceed to §6.

### Result Contract

**Remove the private source tree first.** When `{source_tree}` is set (the [C] of `upstream-checkout.md` read the source there), no later step reads the source: resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} close --tree "{source_tree}"`. Go on whatever it prints. On `left` or `refused`, a command that fails or prints no JSON, or no candidate, record `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "source_tree_not_removed: {source_tree}"` (a later SKF run removes it once it is seven days old). Then set `{source_tree}` to null.

The shared emitter writes the result contract (per `shared/references/output-contract-schema.md`, which resolves relative to the SKF module root: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) and prints the `SKF_AUDIT_RESULT_JSON` envelope from `{run_dir}/result-context.json`, the payload §1b built from the drift report's frontmatter and the classification step 5 saved. Run, in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-audit-skill --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

It writes `{forge_version}/audit-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name) and its `audit-skill-result-latest.json` copy (the record of the last run whose emitter wrote this copy, at a stable path: a copy, not a symlink; a caller reads its own run's `SKF_AUDIT_RESULT_JSON` line), stamps the timestamp, `run_id`, `headless_decisions` and `warnings` into both, and prints the `SKF_AUDIT_RESULT_JSON:` line on stdout. When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here: the shared health check displays it verbatim as the run's last line, so a `claude -p` caller reads `drift_score`, `report_path`, `next_workflow`, `upstream_moved` and `upstream_ref` from the final message. A per-run record that could not be written leaves `result_path` null, and a `-latest` copy that could not be written leaves it set; either adds a `result_file_write_failed` warning to the line, and the run still finishes. If the emitter exits non-zero, fix the value the message on its stderr names (in {outputFile}'s frontmatter, or the saved classification), run §1b again, then run the emitter once more; if it fails again, HALT with **exit 4**, `halt_reason: "write-failed"`, phase `report:result-contract`: the run's result contract could not be written.

**Post-audit hook (optional).** When `{onCompleteCommand}` is not bound, bind it to the `workflow.on_complete` value this prints, or to the one in `{skill-root}/customize.toml` when the resolver cannot run:

```bash
uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow.on_complete
```

If `{onCompleteCommand}` is non-empty, invoke it from `{project-root}` as:

```bash
{onCompleteCommand} --result-path="{result_json_path}"
```

where `{result_json_path}` is the envelope's `result_path`, the per-run record the emitter wrote (skip the hook when it is null). When the hook fails, tell the user it failed and why, and go on: never fail the workflow on a hook error. The hook runs after the result contract is finalized so notifiers, ticket-tracker integrations, or downstream pipelines see a complete record. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 6. Chain to Health Check

Only when the report has been written, presented, and the result contract saved, delete the run folder, whose decisions, warnings and payloads the run no longer needs: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step: do not stop here even though the user-facing summary reads as final.


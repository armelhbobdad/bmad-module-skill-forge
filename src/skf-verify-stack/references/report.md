---
# {outputFile} and {outputFileLatest} resolve from {timestamp} (fixed in
# SKILL.md On Activation §2), {project_slug} (bound at the top of init.md)
# and {outputFolderPath} (On Activation §4), with the same template as the
# init.md frontmatter, so every stage sees the same path. §1 is the only
# place that writes {outputFileLatest}: once the report passes its check.
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Render the user-facing summary in {document_output_language}. -->

# Step 6: Present Report

## STEP GOAL:

Present the complete feasibility report to the user. Display the overall verdict prominently, walk through key findings from each analysis pass, present actionable next steps based on the verdict, write the result contract, and finish.

## Rules

- Focus only on presenting the completed report — no new analysis or changes to verdicts
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is not the terminal step

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Complete Report

Read the entire `{outputFile}` to have all data available for presentation.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

**Validate the report (deterministic gate).** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `report:check`. Then run:

```bash
uv run {validateFeasibilityReportHelper} "{outputFile}" -o "{run_dir}/report-check.json"
```

The script (see `--help`) checks the report against `{feasibilitySchemaRef}`: the five required body sections (`## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`) in canonical order, frontmatter `schemaVersion == "1.0"`, and whatever else its `--help` lists. It writes a JSON verdict to `{run_dir}/report-check.json` (`violation` names the class; the detail fields say what failed; `overallVerdict` and `coveragePercentage` are the report's own) and exits `0` when valid, `1` on a schema violation, `2` when the report cannot be read.

On any non-zero exit, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `report:check`: do not display partial results, and leave `{outputFileLatest}` as it is. Report the specific violation from the JSON:

- a missing or out-of-order section (`missingHeadings` / `orderViolations`);
- a schemaVersion mismatch: "Report frontmatter schemaVersion `{schemaVersionFound}` does not match producer schema `1.0`: report was corrupted between steps. Re-run [VS]." (The producer never proceeds past a schema mismatch.)
- any other detail the JSON carries, such as a missing or doubled canonical verdict table or an unknown verdict token.

**Publish the checked report.** With the gate passed, resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}` (first existing path wins; if no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `report:publish`) and copy the report over its stable `-latest` copy, which consumers such as campaign, create-stack-skill and refine-architecture read:

```bash
python3 {atomicWriteHelper} write --target "{outputFileLatest}" < "{outputFile}"
```

It is a copy, not a symlink (per the shared schema). This is the run's only write of `{outputFileLatest}`: every stage before this one wrote only `{outputFile}`, so a run that halted earlier left the previous finished report at the stable path. On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:publish`, with `"path": "{outputFileLatest}"`; the atomic write leaves the previous copy intact.

With the deterministic gate passed, **extract metrics from `{outputFile}` frontmatter** (per shared schema in `{feasibilitySchemaRef}`): `skillsAnalyzed`, `coveragePercentage`, `pairsVerified` (as `verified_count`), `pairsPlausible` (as `plausible_count`), `pairsRisky` (as `risky_count`), `pairsBlocked` (as `blocked_count`), `requirementsFulfilled` (as `fulfilled_count`), `requirementsPartial` (as `partial_count`), `requirementsNotAddressed` (as `not_addressed_count`), `requirementsPass`, `overallVerdict`, and `recommendationCount`. Use these mapped display names in the summary table and next steps below.

### 2. Present Summary

"**Verify Stack — Feasibility Report**

---

**Overall Verdict: {FEASIBLE / CONDITIONALLY_FEASIBLE / NOT_FEASIBLE}** (tokens are case-sensitive and use underscores per `{feasibilitySchemaRef}`; for user-facing prose you may render them as "Feasible", "Conditionally feasible", or "Not feasible")

| Metric | Value |
|--------|-------|
| **Skills Analyzed** | {skillsAnalyzed} |
| **Coverage** | {coveragePercentage}% |
| **Integrations Verified** | {verified_count} |
| **Integrations Plausible** | {plausible_count} |
| **Integrations Risky** | {risky_count} |
| **Integrations Blocked** | {blocked_count} |
| **Requirements Fulfilled** | {fulfilled_count or 'N/A — no PRD'} |
| **Requirements Partially Fulfilled** | {partial_count or 'N/A — no PRD'} |
| **Requirements Not Addressed** | {not_addressed_count or 'N/A — no PRD'} |

{IF deltaImproved is not null (delta from previous run exists):}
**Delta from Previous Run:**
- Improved: {deltaImproved} items
- Regressed: {deltaRegressed} items
- New: {deltaNew} items
- Unchanged: {deltaUnchanged} items

---"

### 3. Present Detailed Findings

Walk through the highlights: coverage gaps, risky/blocked integrations, and partial/unaddressed requirements (when a PRD pass ran). Cite specific items by name; cap at the top ~5 per category to keep the summary scannable. The full detail is in `{outputFile}`.

### 4. Present Next Steps

Step 05 already wrote a **Suggested next workflow** block (keyed on the case-sensitive `overallVerdict` token) at the end of `## Recommendations`. Surface that block from the §1 load rather than re-deriving it, prefixed with the one-line verdict-specific framing:

- **`FEASIBLE`:** "**Your stack is verified.**" Then give the verdict rationale from the report's `## Executive Summary`: synthesize wrote there what was verified, including when there was no integration pair to verify.
- **`CONDITIONALLY_FEASIBLE`:** "**Your stack is conditionally feasible.** There are {recommendationCount} items to address before proceeding." — then list the specific recommendations from the report's `## Recommendations` section.
- **`NOT_FEASIBLE`:** "**Critical blockers must be resolved.** The stack cannot support the architecture as described." — then list the blocked-integration and missing-skill recommendations from the report's `## Recommendations` section.

### 4b. Result Contract

The shared emitter writes the result contract (per `shared/references/output-contract-schema.md`, which resolves relative to the SKF module root: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) and prints the envelope; this step stages their content, every count from a file a helper wrote. Write `{run_dir}/result-context.json`:

```json
{
  "status": "success",
  "report_path": "{outputFile}",
  "report_latest_path": "{outputFileLatest}",
  "overall_verdict": "<overallVerdict>",
  "coverage_percentage": <coveragePercentage>,
  "recommendation_count": <recommendationCount>,
  "result_contract": {
    "skill": "skf-verify-stack",
    "status": "success",
    "outputs": [{"type": "report", "path": "{outputFile}"}, {"type": "report", "path": "{outputFileLatest}"}],
    "summary": {"overallVerdict": "<overallVerdict>", "coveragePercentage": <coveragePercentage>, "recommendationCount": <recommendationCount>}
  }
}
```

`<overallVerdict>` and `<coveragePercentage>` are the `overallVerdict` (a case-sensitive schema token: `FEASIBLE`, `CONDITIONALLY_FEASIBLE` or `NOT_FEASIBLE`) and `coveragePercentage` §1's check read into `{run_dir}/report-check.json`; `<recommendationCount>` is the report frontmatter's `recommendationCount`, the count synthesize took from its verdict rollup. Then run, in every mode (the emitter writes result files only into a folder that exists):

```bash
mkdir -p "{forge_data_folder}" || uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'result_file_write_failed: cannot create the forge data folder'
uv run {emitEnvelopeHelper} emit --workflow skf-verify-stack --run-dir "{run_dir}" --result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"
```

It writes `{forge_data_folder}/verify-stack-result-{timestamp}.json`, named after the run's own `{timestamp}` (the one the timestamped report carries), and its `verify-stack-result-latest.json` copy, whatever `{outputFolderPath}` is, and prints the `SKF_VERIFY_STACK_RESULT_JSON:` line on stdout. When `{headless_mode}` is true, display the line verbatim before chaining to step 7. A result file that could not be written leaves `result_path` null and a `result_file_write_failed` warning in the line, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:result-contract`, adding `"report_latest_path": "{outputFileLatest}"` to the halt payload: the run's result contract could not be written.

### 5. Finish

"**Feasibility report saved to:** `{outputFile}` (a copy at `{outputFileLatest}`). Ask me to walk through any section of it.

Re-run **[VS] Verify Stack** anytime after making changes to your skills or architecture document.

**Verification workflow complete.**"

If `{workflow.on_complete}` is non-empty, execute it now (e.g. route the verdict onward or trigger a downstream step); in headless, log the action. Then delete the run folder, whose inventory, summaries and payloads the run no longer needs: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`: the health-check step is the true terminal step of this workflow.

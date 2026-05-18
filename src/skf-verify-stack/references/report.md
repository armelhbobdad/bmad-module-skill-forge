---
# {outputFile} and {outputFileLatest} resolve from the activation-stored
# {project_slug}, {timestamp}, and {outputFolderPath} variables (set in
# SKILL.md On Activation §2 + §4) — same template as init.md frontmatter
# so every stage sees the same path.
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
feasibilitySchemaRef: 'src/shared/references/feasibility-report-schema.md'
atomicWriteScript: '{project-root}/src/shared/scripts/skf-atomic-write.py'
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Render the user-facing summary in {document_output_language}. -->

# Step 6: Present Report

## STEP GOAL:

Present the complete feasibility report to the user. Display the overall verdict prominently, walk through key findings from each analysis pass, present actionable next steps based on the verdict, and offer the user options to review the full report or exit.

## Rules

- Focus only on presenting the completed report — no new analysis or changes to verdicts
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

### 1. Load Complete Report

Read the entire `{outputFile}` to have all data available for presentation.

Verify all expected sections are present in order per `{feasibilitySchemaRef}`: `## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`. If any section is missing or out of order, HALT (exit code 5, `halt_reason: "schema-violation"`) and report the schema violation — do not display partial results. In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with `report_path: "{outputFile}"`, `overall_verdict: null`.

**Extract metrics from `{outputFile}` frontmatter** (per shared schema in `{feasibilitySchemaRef}`): `skillsAnalyzed`, `coveragePercentage`, `pairsVerified` (as `verified_count`), `pairsPlausible` (as `plausible_count`), `pairsRisky` (as `risky_count`), `pairsBlocked` (as `blocked_count`), `requirementsFulfilled` (as `fulfilled_count`), `requirementsPartial` (as `partial_count`), `requirementsNotAddressed` (as `not_addressed_count`), `requirementsPass`, `overallVerdict`, and `recommendationCount`. Use these mapped display names in the summary table and next steps below.

**Schema guard:** Verify `schemaVersion == "1.0"` in the frontmatter. If mismatched, HALT (exit code 5, `halt_reason: "schema-violation"`) with "Report frontmatter schemaVersion `{value}` does not match producer schema `1.0` — report was corrupted between steps. Re-run [VS]." (Producer never proceeds past a schema mismatch.) In headless, emit the error envelope.

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

Walk through the highlights — coverage gaps, risky/blocked integrations, and partial/unaddressed requirements (when a PRD pass ran). Cite specific items by name; cap at the top ~5 per category to keep the summary scannable. The full detail is in `{outputFile}` for the user to inspect via the [R] Review menu (§5).

### 4. Present Next Steps

Based on the overall verdict, present the appropriate recommendation:

**IF `overallVerdict == "FEASIBLE"`:**
"**Your stack is verified.** All technologies are covered, integrations are compatible, and requirements are all fulfilled (or requirements pass was skipped).

**Recommended next steps:**
1. **[RA] Refine Architecture** — Produce an implementation-ready architecture document enriched with skill-backed API details
2. **[SS] Create Stack Skill** — compose your individual skills into a unified stack skill, providing the refined architecture doc when prompted
3. **[TS] Test Skill** → **[EX] Export Skill** — Verify completeness and package for distribution"

**IF `overallVerdict == "CONDITIONALLY_FEASIBLE"`:**
"**Your stack is conditionally feasible.** There are {recommendationCount} items to address before proceeding.

**Required actions:**
{List the specific recommendations from Step 05 synthesis}

**After addressing these items:** Re-run **[VS] Verify Stack** to confirm resolution, then proceed to **[RA]**."

**IF `overallVerdict == "NOT_FEASIBLE"`:**
"**Critical blockers must be resolved.** The stack cannot support the architecture as described.

**Critical actions:**
{List the blocked integration recommendations and missing skill actions from Step 05}

**After resolving blockers:** Re-run **[VS] Verify Stack**. Repeat until verdict improves to FEASIBLE or CONDITIONALLY FEASIBLE."

### 4b. Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_data_folder}/verify-stack-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_data_folder}/verify-stack-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include the feasibility report path (both `{outputFile}` and `{outputFileLatest}`) in `outputs`; include `overallVerdict` (`FEASIBLE` / `CONDITIONALLY_FEASIBLE` / `NOT_FEASIBLE`), `coveragePercentage`, and `recommendationCount` in `summary` — use the case-sensitive schema tokens.

Write both JSON files through `python3 {atomicWriteScript} write --target ...` to avoid partial-write corruption. On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) and emit the error envelope.

When `{headless_mode}` is true, also emit the single-line envelope on **stdout** before chaining to step 7 (matches the SKILL.md "Result Contract (Headless)" shape):

```
SKF_VERIFY_STACK_RESULT_JSON: {"status":"success","report_path":"{outputFile}","report_latest_path":"{outputFileLatest}","overall_verdict":"{overallVerdict}","coverage_percentage":{coveragePercentage},"recommendation_count":{recommendationCount},"exit_code":0,"halt_reason":null}
```

`{overallVerdict}` uses the schema tokens (`FEASIBLE` / `CONDITIONALLY_FEASIBLE` / `NOT_FEASIBLE`).

**Result-contract ordering:** The result contract is written exactly once on the first entry to step 6 (the `[X] Exit verification` path). Re-walks of the report via the `[R] Review full report` menu option do NOT regenerate it — the contract captures the run, not the presentation loop. If the user selects `[R]` repeatedly before exiting, the single on-disk contract written on first entry remains authoritative.

### 5. Present Menu

Display: "**[R] Review full report** | **[X] Exit verification**"

#### Menu Handling Logic:

- **IF R:** Walk through the report section by section, presenting each section's content from {outputFile} in a readable format. After completing the walkthrough, redisplay the menu. (Note: the R walkthrough loop terminates only when the user selects X.)
- **IF X:** "**Feasibility report saved to:** `{outputFile}`

Re-run **[VS] Verify Stack** anytime after making changes to your skills or architecture document.

**Verification workflow complete.**"

  Then load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- **GATE [default: X]** — If `{headless_mode}`: auto-proceed with [X] Exit verification, log: "headless: auto-exit past report menu"
- R may be selected multiple times — always walk through the full report
- X triggers the health check, which is the true workflow exit



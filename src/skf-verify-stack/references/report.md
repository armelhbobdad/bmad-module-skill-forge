---
outputFile: '{forge_data_folder}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{forge_data_folder}/feasibility-report-{project_slug}-latest.md'
feasibilitySchemaRef: 'src/shared/references/feasibility-report-schema.md'
atomicWriteScript: '{project-root}/src/shared/scripts/skf-atomic-write.py'
nextStepFile: 'health-check.md'
---

# Step 6: Present Report

## STEP GOAL:

Present the complete feasibility report to the user. Display the overall verdict prominently, walk through key findings from each analysis pass, present actionable next steps based on the verdict, and offer the user options to review the full report or exit.

## Rules

- Focus only on presenting the completed report — no new analysis or changes to verdicts
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Complete Report

Read the entire `{outputFile}` to have all data available for presentation.

Verify all expected sections are present in order per `{feasibilitySchemaRef}`: `## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`. If any section is missing or out of order, HALT and report the schema violation — do not display partial results.

**Extract metrics from `{outputFile}` frontmatter** (per shared schema in `{feasibilitySchemaRef}`): `skillsAnalyzed`, `coveragePercentage`, `pairsVerified` (as `verified_count`), `pairsPlausible` (as `plausible_count`), `pairsRisky` (as `risky_count`), `pairsBlocked` (as `blocked_count`), `requirementsFulfilled` (as `fulfilled_count`), `requirementsPartial` (as `partial_count`), `requirementsNotAddressed` (as `not_addressed_count`), `requirementsPass`, `overallVerdict`, and `recommendationCount`. Use these mapped display names in the summary table and next steps below.

**Schema guard:** Verify `schemaVersion == "1.0"` in the frontmatter. If mismatched, HALT with "Report frontmatter schemaVersion `{value}` does not match producer schema `1.0` — report was corrupted between steps. Re-run [VS]." (Producer never proceeds past a schema mismatch.)

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

Walk through each section briefly, focusing on items that need attention:

"**Coverage Highlights:**
{IF 100% coverage:}
- All referenced technologies have a matching skill

{IF any missing:}
- **Missing:** {list of missing technology names}

**Integration Verdicts:**
{IF all Verified/Plausible:}
- All integration pairs verified or plausible — no blockers

{IF any Risky:}
- **Risky:** {list of risky pairs with brief concern}

{IF any Blocked:}
- **Blocked:** {list of blocked pairs with brief incompatibility}

{IF requirements pass completed:}
**Requirements Gaps:**
{IF all Fulfilled:}
- All stated requirements addressed by the stack

{IF any Partially Fulfilled:}
- **Partially Fulfilled:** {list of partially covered requirements with gap description}

{IF any Not Addressed:}
- **Not Addressed:** {list of unaddressed requirements}"

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

Write both JSON files through `python3 {atomicWriteScript} write --target ...` to avoid partial-write corruption.

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

## CRITICAL STEP COMPLETION NOTE

When the user selects X, this step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md`. After the health check completes, the verify-stack workflow is fully done. The feasibility report at `{outputFile}` (and its stable `-latest.md` copy) contains the full analysis under the fixed headings: Executive Summary, Coverage Analysis, Integration Verdicts, Recommendations, Evidence Sources.


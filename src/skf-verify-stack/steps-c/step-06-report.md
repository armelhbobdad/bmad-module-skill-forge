---
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
nextStepFile: 'shared/health-check.md'
---

# Step 6: Present Report

## STEP GOAL:

Present the complete feasibility report to the user. Display the overall verdict prominently, walk through key findings from each analysis pass, present actionable next steps based on the verdict, and offer the user options to review the full report or exit.

## Rules

- Focus only on presenting the completed report — no new analysis or changes to verdicts
- Chains to shared health check via `{nextStepFile}` after completion

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Complete Report

Read the entire `{outputFile}` to have all data available for presentation.

Verify all expected sections are present: Coverage Matrix, Integration Verdicts, Requirements Coverage (or skipped notation), Synthesis & Recommendations.

**Extract metrics from frontmatter:** Read `skills_analyzed`, `coverage_percentage`, `integrations_verified` (as `verified_count`), `integrations_plausible` (as `plausible_count`), `integrations_risky` (as `risky_count`), `integrations_blocked` (as `blocked_count`), `requirements_fulfilled` (as `fulfilled_count`), `requirements_partial` (as `partial_count`), `requirements_not_addressed` (as `not_addressed_count`), `requirements_pass`, `overall_verdict`, and `recommendation_count`. Use these mapped display names in the summary table and next steps below.

### 2. Present Summary

"**Verify Stack — Feasibility Report**

---

**Overall Verdict: {FEASIBLE / CONDITIONALLY FEASIBLE / NOT FEASIBLE}**

| Metric | Value |
|--------|-------|
| **Skills Analyzed** | {skills_analyzed} |
| **Coverage** | {coverage_percentage}% |
| **Integrations Verified** | {verified_count} |
| **Integrations Plausible** | {plausible_count} |
| **Integrations Risky** | {risky_count} |
| **Integrations Blocked** | {blocked_count} |
| **Requirements Fulfilled** | {fulfilled_count or 'N/A — no PRD'} |
| **Requirements Partially Fulfilled** | {partial_count or 'N/A — no PRD'} |
| **Requirements Not Addressed** | {not_addressed_count or 'N/A — no PRD'} |

{IF delta_improved is not null (delta from previous run exists):}
**Delta from Previous Run:**
- Improved: {delta_improved} items
- Regressed: {delta_regressed} items
- New: {delta_new} items
- Unchanged: {delta_unchanged} items

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

**IF FEASIBLE:**
"**Your stack is verified.** All technologies are covered, integrations are compatible, and requirements are all fulfilled (or requirements pass was skipped).

**Recommended next steps:**
1. **[RA] Refine Architecture** — Produce an implementation-ready architecture document enriched with skill-backed API details
2. **[SS] Create Stack Skill** — compose your individual skills into a unified stack skill, providing the refined architecture doc when prompted
3. **[TS] Test Skill** → **[EX] Export Skill** — Verify completeness and package for distribution"

**IF CONDITIONALLY FEASIBLE:**
"**Your stack is conditionally feasible.** There are {recommendation_count} items to address before proceeding.

**Required actions:**
{List the specific recommendations from Step 05 synthesis}

**After addressing these items:** Re-run **[VS] Verify Stack** to confirm resolution, then proceed to **[RA]**."

**IF NOT FEASIBLE:**
"**Critical blockers must be resolved.** The stack cannot support the architecture as described.

**Critical actions:**
{List the blocked integration recommendations and missing skill actions from Step 05}

**After resolving blockers:** Re-run **[VS] Verify Stack**. Repeat until verdict improves to FEASIBLE or CONDITIONALLY FEASIBLE."

### 4b. Result Contract

Write `{forge_data_folder}/verify-stack-result.json` per `shared/references/output-contract-schema.md`. Include the feasibility report path in `outputs`; include `overall_verdict` (FEASIBLE/CONDITIONALLY FEASIBLE/NOT FEASIBLE), `coverage_percentage`, and `recommendation_count` in `summary`.

### 5. Present Menu

Display: "**[R] Review full report** | **[X] Exit verification**"

#### Menu Handling Logic:

- **IF R:** Walk through the report section by section, presenting each section's content from {outputFile} in a readable format. After completing the walkthrough, redisplay the menu. (Note: the R walkthrough loop terminates only when the user selects X.)
- **IF X:** "**Feasibility report saved to:** `{outputFile}`

Re-run **[VS] Verify Stack** anytime after making changes to your skills or architecture document.

**Verification workflow complete.**"

  Then load and execute `{nextStepFile}` for workflow self-improvement check.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- **GATE [default: X]** — If `{headless_mode}`: auto-proceed with [X] Exit verification, log: "headless: auto-exit past report menu"
- R may be selected multiple times — always walk through the full report
- X triggers the health check, which is the true workflow exit

## CRITICAL STEP COMPLETION NOTE

When the user selects X, this step chains to the shared health check. After the health check completes, the verify-stack workflow is fully done. The feasibility report at `{outputFile}` contains the full analysis: Coverage Matrix, Integration Verdicts, Requirements Coverage, and Synthesis & Recommendations.


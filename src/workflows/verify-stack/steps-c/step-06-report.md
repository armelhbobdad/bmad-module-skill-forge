---
name: 'step-06-report'
description: 'Present the final feasibility report to the user with verdict, findings, and next steps'

outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 6: Present Report

## STEP GOAL:

Present the complete feasibility report to the user. Display the overall verdict prominently, walk through key findings from each analysis pass, present actionable next steps based on the verdict, and offer the user options to review the full report or exit.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a stack verification analyst delivering the final report
- ✅ Present findings clearly and concisely — the user needs to make decisions
- ✅ Next step recommendations must match the verdict exactly

### Step-Specific Rules:

- 🎯 Focus ONLY on presenting the completed report — no new analysis
- 🚫 FORBIDDEN to discover new findings, re-analyze skills, or change verdicts
- 🚫 FORBIDDEN to modify the report content — only read and present
- 📋 This is the FINAL step — no nextStepFile

## EXECUTION PROTOCOLS:

- 🎯 Load and present the complete feasibility report
- 💾 No new content written — report was finalized in Step 05
- 📖 Present summary, detailed findings, and next steps clearly
- 🚫 Read-only presentation — do not alter report data

## CONTEXT BOUNDARIES:

- Available: Complete {outputFile} with all sections from Steps 01-05
- Focus: Clear, actionable presentation of findings
- Limits: Do not add new analysis or change any verdicts
- Dependencies: All previous steps must be complete (Steps 01-05)

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

### 5. Present Menu

Display: "**[R] Review full report** | **[X] Exit verification**"

#### Menu Handling Logic:

- **IF R:** Walk through the report section by section, presenting each section's content from {outputFile} in a readable format. After completing the walkthrough, redisplay the menu. (Note: the R walkthrough loop terminates only when the user selects X.)
- **IF X:** "**Feasibility report saved to:** `{outputFile}`

Re-run **[VS] Verify Stack** anytime after making changes to your skills or architecture document.

**Verification workflow complete.**"

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- R may be selected multiple times — always walk through the full report
- X ends the workflow

## CRITICAL STEP COMPLETION NOTE

This is the final step of the verify-stack workflow. When the user selects X, the workflow is complete. The feasibility report at `{outputFile}` contains the full analysis: Coverage Matrix, Integration Verdicts, Requirements Coverage, and Synthesis & Recommendations.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Complete report loaded and verified for section completeness
- Overall verdict displayed prominently with key metrics
- Delta from previous run shown if applicable
- Detailed findings presented with focus on risky/blocked/missing items
- Next steps match the verdict exactly (FEASIBLE/CONDITIONALLY FEASIBLE/NOT FEASIBLE)
- Menu presented with R and X options
- Report walkthrough available on R selection
- Workflow exits cleanly on X with saved file path

### ❌ SYSTEM FAILURE:

- Discovering new findings or changing verdicts in this step
- Modifying the report content
- Next step recommendations that do not match the verdict
- Not presenting the menu
- Not displaying the report save path on exit
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

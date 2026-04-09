---
outputFile: '{output_folder}/refined-architecture-{project_name}.md'
nextStepFile: 'shared/health-check.md'
---

# Step 6: Present Report

## STEP GOAL:

Present the complete refinement summary to the user. Display counts of gaps filled, issues flagged, and improvements suggested. Provide the output file path and recommend next steps. Offer the user options to review changes in detail or exit. Chains to the shared health check on exit.

## Rules

- Focus only on presenting the completed refinement — no new analysis
- Do not discover new gaps, issues, or improvements, and do not modify the refined document
- Chains to shared health check via `{nextStepFile}` after completion

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Refined Document

Read the `{outputFile}` to have all data available for presentation.

Verify the `## Refinement Summary` section is present. If it is absent, HALT: "⚠️ Refinement Summary not found in `{outputFile}`. Step 05 may not have completed successfully. Re-run [RA] from the beginning."

**Extract metrics from the Refinement Summary section:** Parse `gap_count`, `issue_count`, `improvement_count`, `critical_count`, `major_count`, `minor_count`, `high_count`, `medium_count`, `low_count`, and `skill_count` from the Changes Made table and Evidence Sources table. Use these extracted values in the summary table and next-steps sections below.

### 2. Display Summary

"**Refine Architecture — Refinement Complete**

---

| Metric | Count |
|--------|-------|
| **Gaps Filled** | {gap_count} |
| **Issues Flagged** | {issue_count} (Critical: {critical_count}, Major: {major_count}, Minor: {minor_count}) |
| **Improvements Suggested** | {improvement_count} (High: {high_count}, Medium: {medium_count}, Low: {low_count}) |
| **Skills Used as Evidence** | {skill_count} |

**Evidence Sources:** (which skills contributed evidence)

{Display the Evidence Sources table from the Refinement Summary section of the document}

---

**Your refined architecture is at:** `{outputFile}`

The original architecture content is fully preserved. All refinements are clearly marked with `[!NOTE]`, `[!WARNING]`, and `[!TIP]` callout blocks that you can accept, modify, or remove."

### 3. Present Next Steps

"**Recommended next steps:**

1. **Review the refined document** — accept, modify, or remove individual refinements
2. **[SS] Stack Skill** — compose-mode activates automatically when SS detects existing individual skills without a codebase; provide this refined architecture doc as the architecture document when prompted
3. **Re-run [VS] Verify Stack** if you made changes based on issue corrections — to confirm resolution

{IF issues with Critical severity were found:}
**⚠️ Attention:** {critical_count} critical issue(s) were flagged. These indicate fundamental contradictions between your architecture and the verified API surfaces. Address these before proceeding to stack skill composition."

### 4. Present Menu

Display: "**[R] Review changes in detail** | **[X] Exit refinement**"

#### Menu Handling Logic:

- **IF R:** Walk through each refinement with its full evidence citation:
  1. First, all gaps with their evidence and proposed integration paths
  2. Then, all issues ordered by severity with architecture claim vs. skill reality
  3. Finally, all improvements ordered by value with untapped capability details
  After completing the walkthrough, redisplay the menu.

- **IF X:** "**Refined architecture saved to:** `{outputFile}`

Re-run **[RA] Refine Architecture** anytime after updating your skills or architecture document.

**Architecture refinement complete.**"

  ### Result Contract

  Write `{output_folder}/refine-architecture-result.json` per `shared/references/output-contract-schema.md`. Include the refined architecture doc path in `outputs`; include `gap_count`, `issue_count`, and `improvement_count` in `summary`.

  Then load and execute `{nextStepFile}` for workflow self-improvement check.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- R may be selected multiple times — always walk through all refinements
- X triggers the health check, which is the true workflow exit

## CRITICAL STEP COMPLETION NOTE

When the user selects X, this step chains to the shared health check. After the health check completes, the refine-architecture workflow is fully done. The refined architecture at `{outputFile}` contains the full original content plus all gap-fills, issue annotations, and improvement suggestions backed by skill API evidence.


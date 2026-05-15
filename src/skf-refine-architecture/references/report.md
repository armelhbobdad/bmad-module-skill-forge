---
# {outputFile} resolves from the activation-stored {outputFolderPath}
# variable (set in SKILL.md On Activation §4 from output_folder config +
# customize override).
outputFile: '{outputFolderPath}/refined-architecture-{project_name}.md'
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Render the user-facing summary in {document_output_language}. -->

# Step 6: Present Report

## STEP GOAL:

Present the complete refinement summary to the user. Display counts of gaps filled, issues flagged, and improvements suggested. Provide the output file path and recommend next steps. Offer the user options to review changes in detail or exit. Chains to the shared health check on exit.

## Rules

- Focus only on presenting the completed refinement — no new analysis
- Do not discover new gaps, issues, or improvements, and do not modify the refined document
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is NOT the terminal step

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

  Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{outputFolderPath}/refine-architecture-result-{timestamp}.json` (reuse the activation-stored `{timestamp}`, resolution to seconds) and a copy at `{outputFolderPath}/refine-architecture-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include the refined architecture doc path in `outputs`; include `gap_count`, `issue_count`, and `improvement_count` in `summary`. On any write failure: HALT (exit code 4, `halt_reason: "write-failed"`) and emit the error envelope.

  When `{headless_mode}` is true, also emit the single-line envelope on **stdout** before chaining to step 7 (matches the SKILL.md "Result Contract (Headless)" shape):

  ```
  SKF_REFINE_ARCHITECTURE_RESULT_JSON: {"status":"success","refined_path":"{outputFile}","gap_count":{gap_count},"issue_count":{issue_count},"improvement_count":{improvement_count},"exit_code":0,"halt_reason":null}
  ```

  Then load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- R may be selected multiple times — always walk through all refinements
- X triggers the health check, which is the true workflow exit

## CRITICAL STEP COMPLETION NOTE

When the user selects X, this step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md`. After the health check completes, the refine-architecture workflow is fully done. The refined architecture at `{outputFile}` contains the full original content plus all gap-fills, issue annotations, and improvement suggestions backed by skill API evidence.


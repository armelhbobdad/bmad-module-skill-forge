---
name: 'step-06-report'
description: 'Present refinement summary to user with counts, next steps, and review options'

outputFile: '{output_folder}/refined-architecture-{project_name}.md'
---

# Step 6: Present Report

## STEP GOAL:

Present the complete refinement summary to the user. Display counts of gaps filled, issues flagged, and improvements suggested. Provide the output file path and recommend next steps. Offer the user options to review changes in detail or exit. This is the FINAL step — no nextStepFile.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an architecture refinement analyst delivering the final summary
- ✅ Present findings clearly and concisely — the user needs to decide which refinements to keep
- ✅ Next step recommendations must be specific and actionable

### Step-Specific Rules:

- 🎯 Focus ONLY on presenting the completed refinement — no new analysis
- 🚫 FORBIDDEN to discover new gaps, issues, or improvements
- 🚫 FORBIDDEN to modify the refined document — only read and present
- 📋 This is the FINAL step — no nextStepFile

## EXECUTION PROTOCOLS:

- Load and present the refinement summary from the compiled document
- No new content written — document was finalized in Step 05
- Present summary, next steps, and review options clearly
- Read-only presentation — do not alter document data

## CONTEXT BOUNDARIES:

- Available: Complete {outputFile} with all refinements from Steps 02-05
- Focus: Clear, actionable presentation of refinement results
- Limits: Do not add new analysis or change any refinements
- Dependencies: All previous steps must be complete (Steps 01-05)

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

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the menu
- R may be selected multiple times — always walk through all refinements
- X ends the workflow

## CRITICAL STEP COMPLETION NOTE

This is the final step of the refine-architecture workflow. When the user selects X, the workflow is complete. The refined architecture at `{outputFile}` contains the full original content plus all gap-fills, issue annotations, and improvement suggestions backed by skill API evidence.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Refined document loaded and verified for Refinement Summary section
- Summary displayed with accurate counts for gaps, issues, and improvements
- Output file path displayed prominently
- Next steps presented with specific workflow recommendations
- Critical issues highlighted if present
- Menu presented with R and X options
- Detailed review walkthrough available on R selection with full evidence citations
- Workflow exits cleanly on X with saved file path

### ❌ SYSTEM FAILURE:

- Discovering new findings or changing refinements in this step
- Modifying the refined document content
- Not presenting the menu
- Not displaying the document save path on exit
- Inaccurate counts in the summary
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

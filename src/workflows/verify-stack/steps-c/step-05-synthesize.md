---
name: 'step-05-synthesize'
description: 'Produce overall feasibility verdict, prescriptive recommendations, and diff from previous run'

nextStepFile: './step-06-report.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 5: Synthesize Verdict

## STEP GOAL:

Calculate the overall feasibility verdict based on all three analysis passes, generate prescriptive recommendations for every non-verified finding, check for a previous feasibility report to produce a delta, and compile the synthesis section of the report.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a stack verification analyst delivering the final synthesis
- ✅ The overall verdict must follow the decision logic exactly — no subjectivity
- ✅ Every recommendation must be specific and actionable — not vague advice

### Step-Specific Rules:

- 🎯 Focus ONLY on synthesizing findings from Steps 02-04 into a verdict
- 🚫 FORBIDDEN to discover new findings or re-analyze skills
- 🚫 FORBIDDEN to present the final report to the user — that is Step 06
- 💬 Recommendations must name specific tools, libraries, or actions

## EXECUTION PROTOCOLS:

- 🎯 Apply verdict decision logic to produce FEASIBLE / CONDITIONALLY FEASIBLE / NOT FEASIBLE
- 💾 Append Synthesis & Recommendations section to {outputFile}
- 📖 Check for previous report and generate delta if found
- 🚫 Only synthesis — no new analysis, no final presentation

## CONTEXT BOUNDARIES:

- Available: Coverage matrix (Step 02), integration verdicts (Step 03), requirements coverage (Step 04 if applicable)
- Focus: Verdict calculation, recommendation generation, delta comparison
- Limits: Do not present the full report — that is Step 06
- Dependencies: Steps 02-03 must be complete; Step 04 completed or skipped

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Calculate Overall Verdict

Apply the following decision logic using findings from all completed passes:

**Evaluate in order — the first matching condition wins. Do not continue once a verdict is determined.**

**NOT FEASIBLE (evaluate first):**
- Any integration is **Blocked** → overall verdict is NOT FEASIBLE
- Rationale: a blocked integration represents a fundamental architectural incompatibility. Also note in the rationale any co-occurring Missing skills or Risky integrations so the user understands the full set of problems

**CONDITIONALLY FEASIBLE (evaluate second):**
If ANY of the following apply, the verdict is CONDITIONALLY FEASIBLE. Include ALL matching conditions in the rationale:
- Any technology is **Missing** from coverage (no skill exists)
- Any integration is **Risky** (but none Blocked)
- Requirements have any **Not Addressed** items
- Requirements have any **Partially Fulfilled** items
- Rationale: the stack can work but has gaps, risks, or unverified assumptions that must be addressed

**FEASIBLE (evaluate last):**
- Coverage is 100% (no Missing skills) AND all integrations are Verified or Plausible AND requirements are all Fulfilled (or requirements pass was skipped) AND no Blocked or Risky integrations → overall verdict is FEASIBLE
- Rationale: {IF requirements pass completed:} the stack can support the architecture as described — all requirements fully fulfilled. {IF requirements pass was skipped:} the stack can support the architecture as described — requirements were not evaluated (no PRD provided)

**Post-verdict: Zero integration pairs guard (apply after ANY verdict):**
If zero integration pairs were extracted (all four integration counts are 0) AND the architecture document references 2+ technologies:
- If the verdict was FEASIBLE, override to CONDITIONALLY FEASIBLE
- Regardless of verdict, append this note to the rationale: "No integration claims were found in the architecture document prose. Manual review recommended to confirm that technology relationships are not documented exclusively in diagrams or implied without explicit co-mention."

Store the verdict for use in the report.

### 2. Generate Prescriptive Recommendations

For each non-verified finding across all passes, generate an actionable next step:

**Missing skill (from Step 02):**
- "Run **[CS] Create Skill** or **[QS] Quick Skill** for `{library_name}`, then re-run **[VS]** to verify coverage."

**Risky integration (from Step 03):**
- If protocol mismatch → "Consider adding a bridge layer between `{lib_a}` and `{lib_b}` (e.g., HTTP adapter, message queue). Document the bridge in the architecture."
- If type incompatibility → "Add a serialization/conversion layer between `{lib_a}` and `{lib_b}` to resolve the type mismatch identified in their API surfaces."
- If weak evidence → "Add cross-references between `{lib_a}` and `{lib_b}` skills by re-running **[CS]** with integration context."

**Blocked integration (from Step 03):**
- If language barrier → "Replace `{lib_a}` with a `{lib_b_language}`-compatible alternative, or introduce an IPC/FFI bridge. Redesign the integration path in the architecture document."
- If fundamental incompatibility → "Replace `{blocked_lib}` with an alternative that is compatible with `{other_lib}` in the same domain, or redesign the integration path in the architecture document."

**Not Addressed requirement (from Step 04):**
- "No library in the stack covers `{requirement}`. Evaluate `{category}` libraries that provide this capability, generate a skill, then re-run **[VS]**."

**Partially Fulfilled requirement (from Step 04):**
- "Gap in `{requirement}`: {what_is_missing}. Consider extending `{contributing_skill}` or adding a dedicated library."

**Zero integration pairs (from Step 03):**
- If zero integration pairs were found AND the architecture references 2+ technologies: "No integration claims were found in the architecture document prose. Add explicit prose descriptions of how your technologies interact (not only in diagrams), then re-run **[VS]** to verify integrations."

### 3. Check for Previous Report

Check if a `previous_report` path was recorded in the current report's frontmatter. Since the current workflow run overwrites the report starting in Step 01, the delta feature requires the user to have saved a copy before re-running [VS].

**Note:** The delta feature is only available when the user has manually backed up a prior report and provided the path. To enable delta comparisons, instruct the user to copy their feasibility report (e.g., `feasibility-report-{project_name}-v1.md`) before re-running [VS], then provide the backup path when prompted in Step 01.

**If a previous report is found:**
- Load its verdict, coverage percentage, and integration verdicts
- Generate a delta comparison:
  - **Improved items:** findings that were Risky/Blocked/Missing and are now Verified/Covered
  - **Regressed items:** findings that were Verified/Covered and are now Risky/Blocked/Missing
  - **New items:** findings not present in the previous report
  - **Unchanged items:** count of findings with the same verdict

**If no previous report found:**
- Note: "First verification run — no delta available."

### 4. Compile Synthesis Section

Assemble the following for the report:

**Overall verdict** with rationale citing the decision logic.

**Recommendation list** ordered by priority (count total recommendations as `recommendation_count` — persist this count to `{outputFile}` frontmatter for use in step-06):
1. Blocked integrations (if any)
2. Missing skills
3. Risky integrations
4. Not Addressed requirements
5. Partially Fulfilled requirements

**Delta from previous run** (if applicable):
- Improved, regressed, new, unchanged counts
- Specific items that changed

**Suggested next workflow:**
- FEASIBLE → "Proceed to **[RA] Refine Architecture** to produce an implementation-ready architecture, then **[SS]** to compose your stack skill, then **[TS]** to test and **[EX]** to export."
- CONDITIONALLY FEASIBLE → "Address the {recommendation_count} recommendations above, then re-run **[VS]**. Once all clear, proceed to **[RA]**."
- NOT FEASIBLE → "Critical blockers must be resolved before proceeding. Apply the recommendations above and re-run **[VS]**."

### 5. Append to Report

Write the **Synthesis & Recommendations** section to `{outputFile}`:
- Include overall verdict with rationale
- Include prioritized recommendation list
- Include delta from previous run (if applicable)
- Include suggested next workflow
- **Replace the body placeholder** in the `## Overall Verdict` section: replace `{FEASIBLE / CONDITIONALLY FEASIBLE / NOT FEASIBLE}` and `{1-2 sentence summary}` with the actual calculated verdict and rationale text
- Update frontmatter: append `'step-05-synthesize'` to `stepsCompleted`
- Set `overall_verdict` to the calculated verdict
- Set `recommendation_count` to the total number of recommendations
- If delta was computed (section 3), set `delta_improved`, `delta_regressed`, `delta_new`, `delta_unchanged` in frontmatter to the respective counts
- Verify that `integrations_verified`, `integrations_plausible`, `integrations_risky`, `integrations_blocked` in frontmatter match the counts from Step 03 (these were set in Step 03). If a discrepancy is found, overwrite the frontmatter counts with the values from Step 03 — the report file is the system of record

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Overall verdict calculated using the exact decision logic (not subjective judgment)
- Every non-verified finding has a specific, actionable recommendation
- Recommendations name concrete tools ([CS], [QS], [VS], [RA]) and specific libraries
- Previous report delta generated if applicable
- Synthesis section appended to {outputFile} with verdict, recommendations, and next workflow
- Frontmatter updated with overall_verdict and metric counts
- Auto-proceeded to step 06

### ❌ SYSTEM FAILURE:

- Subjective or vague overall verdict not following the decision logic
- Recommendations without specific actions ("improve the integration")
- Not checking for previous report
- Discovering new findings or re-analyzing skills
- Presenting the full report to the user (that is Step 06)
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

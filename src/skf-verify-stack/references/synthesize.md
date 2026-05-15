---
nextStepFile: 'report.md'
feasibilitySchemaRef: 'src/shared/references/feasibility-report-schema.md'
atomicWriteScript: '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
---

<!-- Config: communicate in {communication_language}. Append the Executive Summary, synthesized verdict, and Recommendations to the report in {document_output_language}. -->

# Step 5: Synthesize Verdict

## STEP GOAL:

Calculate the overall feasibility verdict based on all three analysis passes, generate prescriptive recommendations for every non-verified finding, check for a previous feasibility report to produce a delta, and compile the synthesis section of the report.

## Rules

- Focus only on synthesizing findings from Steps 02-04 into a verdict — do not discover new findings
- Recommendations must name specific tools, libraries, or actions

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Calculate Overall Verdict

**Zero-coverage short-circuit (evaluate before anything else):** Read `coveragePercentage` from `{outputFile}` frontmatter. If `coveragePercentage == 0`, force `overallVerdict: NOT_FEASIBLE` with rationale "no coverage — analysis vacuous: zero generated skills match the architecture's referenced technologies, so integration and requirements verdicts cannot produce meaningful evidence." Skip the remainder of the verdict ladder; proceed directly to section 2 to generate recommendations for the Missing skills surfaced by Step 02.

Apply the following decision logic using findings from all completed passes:

**Evaluate in order — the first matching condition wins. Do not continue once a verdict is determined.**

**NOT_FEASIBLE (evaluate first):**
- Any integration is **Blocked** → overall verdict is `NOT_FEASIBLE`
- Rationale: a blocked integration represents a fundamental architectural incompatibility. Also note in the rationale any co-occurring Missing skills or Risky integrations so the user understands the full set of problems

**CONDITIONALLY_FEASIBLE (evaluate second):**
If ANY of the following apply, the verdict is `CONDITIONALLY_FEASIBLE`. Include ALL matching conditions in the rationale:
- Any technology is **Missing** from coverage (no skill exists)
- Any integration is **Risky** (but none Blocked)
- Requirements have any **Not Addressed** items
- Requirements have any **Partially Fulfilled** items
- Rationale: the stack can work but has gaps, risks, or unverified assumptions that must be addressed

**FEASIBLE (evaluate last):**
- Coverage is 100% (no Missing skills) AND all integrations are `Verified` AND requirements are all Fulfilled (or requirements pass was skipped) AND no Blocked or Risky integrations AND zero pairs were capped at `Plausible` due to missing Check 4 evidence → overall verdict is `FEASIBLE`
- If any pair sits at `Plausible` (including Check-4-missing caps), downgrade to `CONDITIONALLY_FEASIBLE`
- Rationale: {IF requirements pass completed:} the stack can support the architecture as described — all requirements fully fulfilled, every integration pair has a literal cross-reference. {IF requirements pass was skipped:} the stack can support the architecture as described — requirements were not evaluated (no PRD provided)

**Post-verdict: Zero integration pairs guard (apply after ANY verdict):**
If zero integration pairs were extracted (all four integration counts are 0), fire the guard whenever the user continued past the step 2 `[C] Continue anyway` prompt (i.e., any `[C]` continuation from 0% coverage or any other zero-state) — regardless of how many technologies the architecture document references:
- If the verdict was `FEASIBLE`, override to `CONDITIONALLY_FEASIBLE`
- Regardless of verdict, append this note to the rationale: "No integration claims were found in the architecture document prose. Manual review recommended to confirm that technology relationships are not documented exclusively in diagrams or implied without explicit co-mention."

Store the verdict for use in the report.

### 2. Generate Prescriptive Recommendations

For each non-verified finding across all passes, generate an actionable next step:

**Missing skill (from Step 02):**
- "Run **[CS] Create Skill** or **[QS] Quick Skill** for `{library_name}`, then re-run **[VS]** to verify coverage."

**Risky integration (from Step 03):**
- If protocol mismatch → "Consider adding a bridge layer between `{lib_a}` and `{lib_b}` (e.g., HTTP adapter, message queue). Document the bridge in the architecture."
- If type incompatibility → "Add a serialization/conversion layer between `{lib_a}` and `{lib_b}` to resolve the type mismatch identified in their API surfaces."
- If weak evidence (Check 4 missing literal cross-reference) → "Run **[SS] Create Stack Skill** to compose `{lib_a}` and `{lib_b}` and surface integration evidence via the stack manifest, then re-run **[VS]** — the stack manifest's `integration_patterns` block will provide the literal cross-references that promote this pair from `Plausible` to `Verified`."

**Blocked integration (from Step 03):**
- If language barrier → "Replace `{lib_a}` with a `{lib_b_language}`-compatible alternative, or introduce an IPC/FFI bridge. Redesign the integration path in the architecture document."
- If fundamental incompatibility → "Replace `{blocked_lib}` with an alternative that is compatible with `{other_lib}` in the same domain, or redesign the integration path in the architecture document."
- **Named-candidate requirement:** For every Blocked integration where the recommendation proposes replacement, propose AT LEAST ONE named alternative library with a one-line justification (e.g., "Consider `{candidate_name}` — same domain as `{blocked_lib}`, native {target_language} support, compatible with `{other_lib}` via {mechanism}."). If you cannot name at least one concrete candidate, state explicitly: "No named candidate identified — manual research required" and still include one sentence on the selection criteria the user should apply. A Blocked recommendation without either a named candidate or the explicit no-candidate notice is a schema violation.

**Not Addressed requirement (from Step 04):**
- "No library in the stack covers `{requirement}`. Evaluate `{category}` libraries that provide this capability, generate a skill, then re-run **[VS]**."

**Partially Fulfilled requirement (from Step 04):**
- "Gap in `{requirement}`: {what_is_missing}. Consider extending `{contributing_skill}` or adding a dedicated library."

**Zero integration pairs (from Step 03):**
- If zero integration pairs were found AND the architecture references 2+ technologies: "No integration claims were found in the architecture document prose. Add explicit prose descriptions of how your technologies interact (not only in diagrams), then re-run **[VS]** to verify integrations."

### 3. Check for Previous Report

Read `previousReport` from `{outputFile}` frontmatter (set in Step 01). Since the current workflow run overwrites the report starting in Step 01, the delta feature requires the user to have saved a copy before re-running [VS].

**Note:** The delta feature is only available when the user has manually backed up a prior report and provided the path. To enable delta comparisons, instruct the user to copy their feasibility report (e.g., `feasibility-report-{projectSlug}-v1.md`) before re-running [VS], then provide the backup path when prompted in Step 01.

**If a previous report is found:**
- Load its verdict, coverage percentage, integration verdicts, and per-skill `confidence_tier` values (if captured in the previous report's inventory block)
- Generate a delta comparison:
  - **Improved items:** findings that were Risky/Blocked/Missing and are now Verified/Covered
  - **Regressed items:** findings that were Verified/Covered and are now Risky/Blocked/Missing
  - **Tier downgrades (regression):** for each skill present in both runs, compare current `confidence_tier` against previous. A downgrade (e.g., Tier 1 → Tier 2, or T1 → T1-low) is a regression — flag explicitly in the delta section with rationale "skill `{skill_name}` regressed from `{prev_tier}` to `{curr_tier}` — re-extract with [CS] at the prior tier level".
  - **New items:** findings not present in the previous report
  - **Unchanged items:** count of findings with the same verdict

**If no previous report found:**
- Note: "First verification run — no delta available."

### 4. Compile Synthesis Section

Assemble the following for the report:

**Overall verdict** with rationale citing the decision logic.

**Recommendation list** ordered by priority (count total recommendations as `recommendationCount` — persist this count to `{outputFile}` frontmatter for use in step 6):
1. Blocked integrations (if any)
2. Missing skills
3. Risky integrations
4. Not Addressed requirements
5. Partially Fulfilled requirements

**Delta from previous run** (if applicable):
- Improved, regressed, new, unchanged counts
- Specific items that changed

**Suggested next workflow** (match on case-sensitive `overallVerdict` token):
- `FEASIBLE` → "Proceed to **[RA] Refine Architecture** to produce an implementation-ready architecture, then **[SS]** to compose your stack skill, then **[TS]** to test and **[EX]** to export."
- `CONDITIONALLY_FEASIBLE` → "Address the {recommendationCount} recommendations above, then re-run **[VS]**. Once all clear, proceed to **[RA]**."
- `NOT_FEASIBLE` → "Critical blockers must be resolved before proceeding. Apply the recommendations above and re-run **[VS]**."

### 5. Append to Report

Write the **Recommendations** and **Evidence Sources** sections to `{outputFile}` (per the fixed heading order in `{feasibilitySchemaRef}`):
- Include overall verdict with rationale in the `## Executive Summary` section (replace the placeholder text from the template)
- Include prioritized recommendation list under `## Recommendations`
- Include delta from previous run (if applicable) under `## Recommendations` as a subsection
- Include suggested next workflow at the end of `## Recommendations`
- Populate `## Evidence Sources` with per-skill citations (SKILL.md path, `metadata_schema_version`, `confidence_tier`, stack manifest if any) and architecture/PRD doc paths
- Update frontmatter (shared-schema keys):
  - Append `'synthesize'` to `stepsCompleted`
  - Set `overallVerdict` to one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE`, `NOT_FEASIBLE` (case-sensitive, underscores — NOT spaces)
  - Set `recommendationCount` to the total number of recommendations
  - If delta was computed (section 3), set `deltaImproved`, `deltaRegressed`, `deltaNew`, `deltaUnchanged`
  - Verify that `pairsVerified`, `pairsPlausible`, `pairsRisky`, `pairsBlocked` match the counts from Step 03 (these were set in Step 03). If a discrepancy is found, overwrite the frontmatter counts with the values from Step 03 — the report file is the system of record
- **Overall verdict enforcement (schema producer obligation):**
  - If any pair has Check 4 missing/weak AND was capped at `Plausible`, that alone does NOT force `NOT_FEASIBLE`, but `FEASIBLE` requires zero such pairs
  - `FEASIBLE` requires 100% coverage AND zero Blocked pairs AND zero Check-4-missing pairs — otherwise downgrade to `CONDITIONALLY_FEASIBLE`
  - `coveragePercentage == 0` forces `NOT_FEASIBLE` (per section 1 short-circuit)
- Pipe the updated full content through `python3 {atomicWriteScript} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.


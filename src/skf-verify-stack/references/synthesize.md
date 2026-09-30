---
nextStepFile: 'report.md'
verdictRollupScript: 'scripts/skf-verdict-rollup.py'
reportDeltaScript: 'scripts/skf-report-delta.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
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

### 1. Calculate Overall Verdict

**The verdict token is deterministic: do not walk the ladder in prose.** All three passes have already persisted their counts in `{outputFile}` frontmatter: `coveragePercentage`, `coverageMissing` and `coverageCovered` (step 2's tally), `pairsBlocked`/`pairsRisky`/`pairsPlausible`/`pairsVerified`, and `requirementsPass` + `requirementsNotAddressed`/`requirementsPartial`. Rolling them up into one token has a single correct answer per input, so delegate it. Assemble the counts and run:

```bash
echo '<counts JSON>' | uv run {verdictRollupScript} --stdin
```

Input keys: `coveragePercentage`, `missingCount` ← `coverageMissing`, `coveredCount` ← `coverageCovered`, `pairsBlocked`, `pairsRisky`, `pairsPlausible`, `pairsVerified`; plus, only when the requirements pass ran (`requirementsPass == "completed"`), `requirementsEvaluated: true` with `requirementsNotAddressed`/`requirementsPartial`. Half-up rounding can leave `coveragePercentage == 100` with one technology still Missing, so the percentage stands in for neither count. The script (run `uv run {verdictRollupScript} --help` for the ladder) returns `overallVerdict` (one of `FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`), `matchedConditions` (the condition codes that fired) and `zeroPairsGuardFired`. When it exits non-zero, it rejected its input and says why (its JSON `error`, or a usage line for an empty input): fix the input and run it again.

Technologies marked **Replaced** in Step 02 are intentionally being removed and are already excluded from `missingCount` and the coverage denominator: they never trigger `CONDITIONALLY_FEASIBLE` or a [CS]/[QS] recommendation.

**Write the rationale** from `matchedConditions`, naming the specific findings behind each code:
- `zero-coverage` → "no coverage, analysis vacuous: zero generated skills match the architecture's referenced technologies, so integration and requirements verdicts cannot produce meaningful evidence." Then proceed directly to section 2 to generate recommendations for the Missing and/or Replaced technologies surfaced by Step 02.
- `blocked-integration` → a blocked integration is a fundamental architectural incompatibility; name each Blocked pair and note any co-occurring `missing-coverage`/`risky-integration` codes so the user sees the full set of problems.
- `missing-coverage` / `risky-integration` / `requirements-not-addressed` / `requirements-partial` / `plausible-cap` → the stack can work but has gaps, risks, or unverified assumptions that must be addressed; name the specific items behind each code.
- `zero-integration-pairs` (whatever the verdict) → append: "No integration pair between two covered technologies was found in the architecture document prose, so no integration was verified. Relationships drawn only in diagrams, or implied without an explicit co-mention, are not checked: describe them in prose to have them verified."
- No codes (`FEASIBLE`) → the stack can support the architecture as described: every live technology has a skill, every integration pair is `Verified` (at least one of its two skills cites the other literally), and {IF requirements pass completed:} every requirement is fulfilled {IF requirements pass was skipped:} requirements were not evaluated (no PRD provided). {IF `pairsVerified` is 0:} The architecture names a single live technology, so it has no integration pair to verify.

Store the verdict for use in the report.

### 2. Generate Prescriptive Recommendations

For each non-verified finding across all passes, generate an actionable next step:

**Missing skill (from Step 02):**
- "Run **[CS] Create Skill** or **[QS] Quick Skill** for `{library_name}`, then re-run **[VS]** to verify coverage."

**Replaced / being-removed technology (from Step 02):**
- "`{library_name}` is marked for removal/replacement in the architecture document — no skill is needed. Remove it from the architecture document (or, if it is in fact staying, correct the document to drop the removal marker), then re-run **[VS]**."
- Do not emit a [CS]/[QS] recommendation for a Replaced technology — forging a skill for a technology that is being deleted is exactly the misfire this category prevents.

**Risky integration (from Step 03):**
- If protocol mismatch → "Consider adding a bridge layer between `{lib_a}` and `{lib_b}` (e.g., HTTP adapter, message queue). Document the bridge in the architecture."
- If type incompatibility → "Add a serialization/conversion layer between `{lib_a}` and `{lib_b}` to resolve the type mismatch identified in their API surfaces."

**Plausible integration (from Step 03; neither skill cites the other):**
- "Neither `{lib_a}`'s nor `{lib_b}`'s SKILL.md names the other, so the pair stays `Plausible` until one of them does. When a page documents how the two work together (a `{lib_a}` guide that uses `{lib_b}`, say), add it to that skill's brief as a `doc_urls` entry with **[BS] Brief Skill**, re-create the skill with **[CS] Create Skill**, then re-run **[VS]**. Until then, prototype the integration before you rely on it."

**Blocked integration (from Step 03):**
- If language barrier → "Replace `{lib_a}` with a `{lib_b_language}`-compatible alternative, or introduce an IPC/FFI bridge. Redesign the integration path in the architecture document."
- If fundamental incompatibility → "Replace `{blocked_lib}` with an alternative that is compatible with `{other_lib}` in the same domain, or redesign the integration path in the architecture document."
- **Named-candidate requirement:** For every Blocked integration where the recommendation proposes replacement, propose AT LEAST ONE named alternative library with a one-line justification (e.g., "Consider `{candidate_name}` — same domain as `{blocked_lib}`, native {target_language} support, compatible with `{other_lib}` via {mechanism}."). If you cannot name at least one concrete candidate, state explicitly: "No named candidate identified — manual research required" and still include one sentence on the selection criteria the user should apply. A Blocked recommendation without either a named candidate or the explicit no-candidate notice is a schema violation.

**Not Addressed requirement (from Step 04):**
- "No library in the stack covers `{requirement}`. Evaluate `{category}` libraries that provide this capability, generate a skill, then re-run **[VS]**."

**Partially Fulfilled requirement (from Step 04):**
- "Gap in `{requirement}`: {what_is_missing}. Consider extending `{contributing_skill}` or adding a dedicated library."

**Zero integration pairs (from Step 03):**
- When `matchedConditions` holds `zero-integration-pairs` (no pair across two or more covered technologies): "No integration claims were found in the architecture document prose. Add explicit prose descriptions of how your technologies interact (not only in diagrams), then re-run **[VS]** to verify integrations."

### 3. Check for Previous Report

Read `previousReport` from `{outputFile}` frontmatter (set in step 1): an earlier run's report, or empty when there is none or the user skipped the comparison. Step 1 compares against the newest earlier report unless the user names another; to compare against an older run, pass its timestamped report in step 1.

**If `previousReport` is set:** comparing two runs has one correct answer, and so does reading their findings: each sits in a table with a pinned header. The delta helper reads both reports itself: the Coverage Analysis rows and the canonical `| lib_a | lib_b | verdict | rationale |` table of each, and the `evidence_tier` column of the previous report's `## Evidence Sources` table (section 5 writes it). This run's tiers go in as JSON: `currentTiers` maps each skill in `skill_inventory` to its `evidence_tier`, on the one scale `T1`, `T1-low`, `T2` and `T3`. Never pass `confidence_tier`: a single skill records its forge tier there (Quick to Deep) and a stack a T-code, so across the roster its values sit on two scales that do not compare. Run:

```bash
echo '<tiers JSON>' | uv run {reportDeltaScript} --previous-report "{previousReport}" --current-report "{outputFile}" --stdin
```

with `{"currentTiers": {"<skill>": "<evidence_tier>", …}}` as `<tiers JSON>`. The script (run `uv run {reportDeltaScript} --help` for the contract and rankings) returns `improved`/`regressed`/`unchanged`/`new`/`dropped`/`replaced` label lists with counts, `tierDowngrades` (each `{skill, from, to}`: a drop along `T1` > `T1-low` > `T2` > `T3`, such as `T1` to `T1-low`, counts as a regression) and `previousTiersRecorded`. Branch on its exit code and its JSON `code`:

- Exit 0: render the delta section from those results. When `previousTiersRecorded` is false (a report written before tiers were recorded), add "The previous report records no skill tiers, so tier changes were not compared." For each tier downgrade, flag: "skill `{skill}` evidence fell from `{from}` to `{to}`: check the forge tier with [SF] Setup Forge, then re-create the skill at its earlier tier with [CS] ([SS] for a stack skill)".
- `UNKNOWN_TIER` (exit 2): the previous report's tier table holds a token outside the scale. Run it again with `--no-tiers` added, render the delta section from that run, and add "Tier changes were not compared: {error}".
- `INVALID_REPORT` (exit 2): its `error` names a report that is not read (a `schemaVersion` other than `1.0`, a missing coverage or verdict table, the verdict table twice, or a verdict outside its token set). Write "No delta: {error}" in place of the delta section.
- `INVALID_INPUT` (exit 2): `<tiers JSON>` was built wrong; fix it and run again.
- `HELPER_MISSING` (exit 1): the shared report reader it loads is not installed; HALT per the Workflow Rules (exit code 3, `halt_reason: "resolution-failure"`).

**If `previousReport` is empty:** note "First verification run: no delta available."

### 4. Compile Synthesis Section

Assemble the following for the report:

**Overall verdict** with rationale citing the decision logic.

**Recommendation list** ordered by priority (count total recommendations as `recommendationCount` — persist this count to `{outputFile}` frontmatter for use in step 6):
1. Blocked integrations (if any)
2. Missing skills
3. Risky integrations
4. Plausible integrations
5. Zero integration pairs
6. Not Addressed requirements
7. Partially Fulfilled requirements

**Delta from previous run** (if applicable):
- Improved, regressed, new, unchanged counts
- Specific items that changed

**Suggested next workflow** (match on case-sensitive `overallVerdict` token):
- `FEASIBLE` → "Proceed to **[RA] Refine Architecture** to produce an implementation-ready architecture, then **[SS]** to compose your stack skill, then **[TS]** to test and **[EX]** to export."
- `CONDITIONALLY_FEASIBLE` → "Address the {recommendationCount} recommendations above, then re-run **[VS]**. Once all clear, proceed to **[RA]**."
- `NOT_FEASIBLE` → "Critical blockers must be resolved before proceeding. Apply the recommendations above and re-run **[VS]**."

### 5. Append to Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Recommendations** and **Evidence Sources** sections to `{outputFile}` (per the fixed heading order in `{feasibilitySchemaRef}`):
- Include overall verdict with rationale in the `## Executive Summary` section (replace the placeholder text from the template)
- Include prioritized recommendation list under `## Recommendations`
- Include delta from previous run (if applicable) under `## Recommendations` as a subsection
- Include suggested next workflow at the end of `## Recommendations`
- Populate `## Evidence Sources`: the template already holds its table, with the header `| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |`. Fill it in place with one row per skill in `skill_inventory` (`name`, `evidence_tier`, `confidence_tier` or `none`, `metadata_schema_version` or `none`, and `{skills_output_folder}/{path}/SKILL.md`); the next run's delta reads its `evidence_tier` column (section 3). Below it, list the stack manifest, if any, and the architecture and PRD document paths.
- Update frontmatter (shared-schema keys):
  - Append `'synthesize'` to `stepsCompleted`
  - Set `overallVerdict` to one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE`, `NOT_FEASIBLE` (case-sensitive, underscores not spaces)
  - Set `recommendationCount` to the total number of recommendations
  - If delta was computed (section 3), set `deltaImproved`, `deltaRegressed`, `deltaNew`, `deltaUnchanged` from the delta helper's `improvedCount` / `regressedCount` / `newCount` / `unchangedCount`
  - Verify that `pairsVerified`, `pairsPlausible`, `pairsRisky`, `pairsBlocked` match the counts from Step 03 (these were set in Step 03). If a discrepancy is found, overwrite the frontmatter counts with the values from Step 03 — the report file is the system of record
- Write the `overallVerdict` the §1 rollup returned, verbatim.
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.


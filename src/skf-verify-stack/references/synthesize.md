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

**The verdict token is deterministic — do not walk the ladder in prose.** All three passes have already persisted their counts (`coveragePercentage`, `pairsBlocked`/`pairsRisky`/`pairsPlausible`/`pairsVerified`, `requirementsPass` + `requirementsNotAddressed`/`requirementsPartial` in `{outputFile}` frontmatter; the Missing technology count in the Coverage Analysis table). Rolling those already-decided counts up into one token has a single correct answer per input, so delegate it. Count Missing rows directly from the Coverage table — half-up rounding can leave `coveragePercentage == 100` with one technology still Missing — assemble the counts, and run:

```bash
echo '<counts JSON>' | uv run {verdictRollupScript} --stdin
```

Input keys: `coveragePercentage`, `missingCount`, `pairsBlocked`, `pairsRisky`, `pairsPlausible`, `pairsVerified`; plus, only when the requirements pass ran (`requirementsPass == "completed"`), `requirementsEvaluated: true` with `requirementsNotAddressed`/`requirementsPartial`; plus `continuedPastZeroState: true` if the user pressed `[C] Continue anyway` past a step-2 zero-state gate (all-Replaced or 0%-coverage). The script (run `uv run {verdictRollupScript} --help` for the contract) returns `overallVerdict` (one of `FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`), `matchedConditions` (the condition codes that fired), and `zeroPairsGuardFired`. If `uv` is unavailable (e.g. claude.ai web), apply the ladder below inline.

**The ladder it applies (documented so the rationale can cite it — the script is the executor; evaluate top-to-bottom, first match wins):**
- `coveragePercentage == 0` → `NOT_FEASIBLE` (short-circuit: no live coverage, analysis vacuous).
- Any Blocked integration → `NOT_FEASIBLE` (fundamental architectural incompatibility).
- Any Missing technology, any Risky integration, or — when requirements ran — any Not Addressed / Partially Fulfilled requirement → `CONDITIONALLY_FEASIBLE`.
- Otherwise → `FEASIBLE`, but any pair capped at `Plausible` (including Check-4-missing caps) downgrades to `CONDITIONALLY_FEASIBLE`.
- Post-verdict guard: when all four integration counts are 0 and the user continued past a step-2 zero-state gate, `zeroPairsGuardFired` is true — a `FEASIBLE` verdict is overridden to `CONDITIONALLY_FEASIBLE`.

Technologies marked **Replaced** in Step 02 are intentionally being removed and are already excluded from `missingCount` and the coverage denominator — they never trigger `CONDITIONALLY_FEASIBLE` or a [CS]/[QS] recommendation.

**Write the rationale** from `matchedConditions`, naming the specific findings behind each code:
- `zero-coverage` → "no coverage — analysis vacuous: zero generated skills match the architecture's referenced technologies, so integration and requirements verdicts cannot produce meaningful evidence." Then proceed directly to section 2 to generate recommendations for the Missing and/or Replaced technologies surfaced by Step 02.
- `blocked-integration` → a blocked integration is a fundamental architectural incompatibility; name each Blocked pair and note any co-occurring `missing-coverage`/`risky-integration` codes so the user sees the full set of problems.
- `missing-coverage` / `risky-integration` / `requirements-not-addressed` / `requirements-partial` / `plausible-cap` → the stack can work but has gaps, risks, or unverified assumptions that must be addressed; name the specific items behind each code.
- No codes (`FEASIBLE`) → {IF requirements pass completed:} the stack can support the architecture as described — all requirements fully fulfilled, every integration pair has a literal cross-reference. {IF requirements pass was skipped:} the stack can support the architecture as described — requirements were not evaluated (no PRD provided).
- `zero-integration-pairs` (present whenever the guard fired, regardless of verdict) → append: "No integration claims were found in the architecture document prose. Manual review recommended to confirm that technology relationships are not documented exclusively in diagrams or implied without explicit co-mention."

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

Read `previousReport` from `{outputFile}` frontmatter (set in Step 01). Each run writes a new timestamped `feasibility-report-{projectSlug}-{timestamp}.md`, so prior reports persist on disk automatically — Step 01 auto-discovers the most recent one for delta comparison when no path is supplied. `previousReport` holds the resolved path, or is empty when no prior report exists or the user skipped the comparison.

**Note:** A manual backup is only needed to compare against a *specific older* snapshot rather than the most recent prior run; provide that backup path when prompted in Step 01.

**If a previous report is found:**
- Extract from both reports (current run + the previous report's tables/inventory block): the coverage findings (`{technology, verdict}`), the integration findings (`{libA, libB, verdict}`), and each skill's `confidence_tier`. Reading the tables is judgment; classifying the difference is not — so hand the two extracted finding sets to the delta helper rather than diffing in prose (matching pair keys and applying the verdict ranking by hand drifts between runs).
- Serialize as `{"previous": {"coverage": […], "integration": […]}, "current": {…}, "previousTiers": {skill: tier}, "currentTiers": {…}}` and run:

  ```bash
  echo '<delta JSON>' | uv run {reportDeltaScript} --stdin
  ```

  The script (run `uv run {reportDeltaScript} --help` for the contract and rankings) returns `improved`/`regressed`/`unchanged`/`new`/`dropped`/`replaced` label lists with counts, plus `tierDowngrades` (each `{skill, from, to}`) — a tier drop (Tier 1 → Tier 2, or T1 → T1-low) counts as a regression. If `uv` is unavailable, apply the ranking from `--help` inline (coverage Missing<Covered; integration Blocked<Risky<Plausible<Verified; tier T2<T1-low<T1; Replaced findings bucketed, not scored).
- Render the delta section from those results. For each tier downgrade, flag: "skill `{skill}` regressed from `{from}` to `{to}` — re-extract with [CS] at the prior tier level".

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

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Recommendations** and **Evidence Sources** sections to `{outputFile}` (per the fixed heading order in `{feasibilitySchemaRef}`):
- Include overall verdict with rationale in the `## Executive Summary` section (replace the placeholder text from the template)
- Include prioritized recommendation list under `## Recommendations`
- Include delta from previous run (if applicable) under `## Recommendations` as a subsection
- Include suggested next workflow at the end of `## Recommendations`
- Populate `## Evidence Sources` with per-skill citations (SKILL.md path, `metadata_schema_version`, `confidence_tier`, stack manifest if any) and architecture/PRD doc paths
- Update frontmatter (shared-schema keys):
  - Append `'synthesize'` to `stepsCompleted`
  - Set `overallVerdict` to one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE`, `NOT_FEASIBLE` (case-sensitive, underscores not spaces)
  - Set `recommendationCount` to the total number of recommendations
  - If delta was computed (section 3), set `deltaImproved`, `deltaRegressed`, `deltaNew`, `deltaUnchanged` from the delta helper's `improvedCount` / `regressedCount` / `newCount` / `unchangedCount`
  - Verify that `pairsVerified`, `pairsPlausible`, `pairsRisky`, `pairsBlocked` match the counts from Step 03 (these were set in Step 03). If a discrepancy is found, overwrite the frontmatter counts with the values from Step 03 — the report file is the system of record
- **Overall verdict enforcement (schema producer obligation):** write the `overallVerdict` the §1 rollup script returned verbatim — do not re-derive the ladder here. §1 (via `{verdictRollupScript}`) is its single source of truth (the 100%-coverage + zero-Blocked + zero-Check-4-missing bar for `FEASIBLE`, and the `coveragePercentage == 0` → `NOT_FEASIBLE` short-circuit included).
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.


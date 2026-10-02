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
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
inventoryFile: '{run_dir}/skill-inventory.json'
---

<!-- Config: communicate in {communication_language}. Append the Executive Summary, synthesized verdict, and Recommendations to the report in {document_output_language}. -->

# Step 5: Synthesize Verdict

## STEP GOAL:

Calculate the overall feasibility verdict based on all three analysis passes, generate prescriptive recommendations for every non-verified finding, check for a previous feasibility report to produce a delta, and compile the synthesis section of the report.

## Rules

- Focus only on synthesizing findings from Steps 02-04 into a verdict — do not discover new findings
- Recommendations must name specific tools, libraries, or actions

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Calculate Overall Verdict

**The verdict token is deterministic: do not walk the ladder in prose.** All three passes have already persisted their counts in the `{outputFile}` frontmatter, each from its tally helper. Rolling them up into one token has a single correct answer per input, and so has the number of recommendations they call for, so delegate both, and let the script read the counts from the report itself:

```bash
uv run {verdictRollupScript} --report "{outputFile}"
```

`--report` reads `coverageCovered`, `coverageMissing` and the other counts steps 2 to 4 persisted, once `stepsCompleted` lists `coverage`, `integrations` and `requirements`; `uv run {verdictRollupScript} --help` gives each key, the input it fills and the ladder. The script returns `overallVerdict` (one of `FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`), `matchedConditions` (the condition codes that fired), `zeroPairsGuardFired`, `recommendations` (how many recommendations of each kind section 2 writes) and `recommendationCount` (their sum). Branch on its exit code and its JSON `code`:

- `HELPER_MISSING` (exit 1): the shared report reader it loads is not installed; HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:rollup`.
- `INVALID_REPORT` or `INVALID_INPUT` (exit 2): its `error` names a stage `stepsCompleted` does not list, a count a stage left out of the frontmatter, or counts that disagree; HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `synthesize:rollup`, naming that `error`.
- Any other non-zero exit (no JSON on stdout): HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:rollup` with its stderr.

Technologies marked **Replaced** in Step 02 are intentionally being removed and are already excluded from `missingCount` and the coverage denominator: they never trigger `CONDITIONALLY_FEASIBLE` or a [CS]/[QS] recommendation.

**Write the rationale** from `matchedConditions`, naming the specific findings behind each code:
- `zero-coverage` → "no coverage, analysis vacuous: zero generated skills match the architecture's referenced technologies, so integration and requirements verdicts cannot produce meaningful evidence." Then proceed directly to section 2 to generate recommendations for the Missing and/or Replaced technologies surfaced by Step 02.
- `blocked-integration` → a blocked integration is a fundamental architectural incompatibility; name each Blocked pair and note any co-occurring `missing-coverage`/`risky-integration` codes so the user sees the full set of problems.
- `missing-coverage` / `risky-integration` / `requirements-not-addressed` / `requirements-partial` / `plausible-cap` → the stack can work but has gaps, risks, or unverified assumptions that must be addressed; name the specific items behind each code.
- `zero-integration-pairs` (whatever the verdict) → append: "No integration pair between two covered technologies was found in the architecture document prose, so no integration was verified. Relationships drawn only in diagrams, or implied without an explicit co-mention, are not checked: describe them in prose to have them verified."
- No codes (`FEASIBLE`) → the stack can support the architecture as described: every live technology has a skill, every integration pair is `Verified` (at least one of its two skills cites the other literally), and {IF requirements pass completed:} every requirement is fulfilled {IF requirements pass was skipped:} requirements were not evaluated (no PRD provided). {IF `pairsVerified` is 0:} The architecture names a single live technology, so it has no integration pair to verify.

Store the verdict for use in the report.

### 2. Generate Prescriptive Recommendations

For each non-verified finding across all passes, generate one actionable next step: exactly the number of each kind the §1 rollup's `recommendations` gives (one per Blocked, Missing, Replaced, Risky and Plausible item, one for the zero-pairs note, and one per Not Addressed or Partially Fulfilled requirement when the requirements pass ran), so the list matches the `recommendationCount` the report and the envelope carry:

**Missing skill (from Step 02):**
- "Run **[CS] Create Skill** or **[QS] Quick Skill** for `{library_name}`, then re-run **[VS]** to verify coverage."

**Replaced / being-removed technology (from Step 02):**
- "`{library_name}` is marked for removal/replacement in the architecture document — no skill is needed. Remove it from the architecture document (or, if it is in fact staying, correct the document to drop the removal marker), then re-run **[VS]**."
- Do not emit a [CS]/[QS] recommendation for a Replaced technology — forging a skill for a technology that is being deleted is exactly the misfire this category prevents.

**Risky integration (from Step 03):**
- If protocol mismatch → "Consider adding a bridge layer between `{lib_a}` and `{lib_b}` (e.g., HTTP adapter, message queue). Document the bridge in the architecture."
- If type incompatibility → "Add a serialization/conversion layer between `{lib_a}` and `{lib_b}` to resolve the type mismatch identified in their API surfaces."
- If circular dependency (a step 3 cycle row: `cycle` in its `lib_a`, the chain in its `lib_b`) → "`{A → B → C → A}` form a circular integration dependency: each skill's SKILL.md cites the next. Check that the architecture gives the calls between them one direction, or place an adapter between them, before you build on it."
- If a skill changed mid-run (the rationale "skill modified mid-run") → "`{skill}` changed while this run read it, so `{lib_a}` ↔ `{lib_b}` was not rated: re-run **[VS]**."

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

**If `previousReport` is set:** comparing two runs has one correct answer, and so does reading their findings: each sits in a table with a pinned header. The delta helper reads both reports itself: the Coverage Analysis rows and the canonical `| lib_a | lib_b | verdict | rationale |` table of each, and the `evidence_tier` column of the previous report's `## Evidence Sources` table (section 5 writes it). It reads this run's tiers, each skill's `evidence_tier`, from `{inventoryFile}`. Run:

```bash
uv run {reportDeltaScript} --previous-report "{previousReport}" --current-report "{outputFile}" --inventory "{inventoryFile}"
```

The script (run `uv run {reportDeltaScript} --help` for the contract and rankings) returns `improved`/`regressed`/`unchanged`/`new`/`dropped`/`replaced` label lists with counts, `tierDowngrades` (each `{skill, from, to}`: a drop along `T1` > `T1-low` > `T2` > `T3`, such as `T1` to `T1-low`, counts as a regression) and `previousTiersRecorded`. Branch on its exit code and its JSON `code`:

- Exit 0: render the delta section from those results. When `previousTiersRecorded` is false (a report written before tiers were recorded), add "The previous report records no skill tiers, so tier changes were not compared." For each tier downgrade, flag: "skill `{skill}` evidence fell from `{from}` to `{to}`: check the forge tier with [SF] Setup Forge, then re-create the skill at its earlier tier with [CS] ([SS] for a stack skill)".
- `UNKNOWN_TIER` or `INVALID_INPUT` (exit 2): a tier outside the scale, or an `{inventoryFile}` it cannot read. Run it again with `--no-tiers` added, render the delta section from that run, and add "Tier changes were not compared: {error}".
- `INVALID_REPORT` (exit 2): its `error` names a report that is not read (a `schemaVersion` other than `1.0`, a missing coverage or verdict table, the verdict table twice, or a verdict outside its token set). Write "No delta: {error}" in place of the delta section.
- `HELPER_MISSING` (exit 1): the shared report reader it loads is not installed; HALT per the Workflow Rules (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:delta`.

**If `previousReport` is empty:** note "First verification run: no delta available."

### 4. Compile Synthesis Section

Assemble the following for the report:

**Overall verdict** with rationale citing the decision logic.

**Recommendation list** ordered by priority, the order the §1 rollup's `recommendations` lists its kinds in (`recommendationCount` is the §1 rollup's `recommendationCount`, never a count of your own; section 5 persists it for step 6):
1. Blocked integrations (if any)
2. Missing skills
3. Replaced technologies
4. Risky integrations
5. Plausible integrations
6. Zero integration pairs
7. Not Addressed requirements
8. Partially Fulfilled requirements

**Delta from previous run** (if applicable):
- Improved, regressed, new, unchanged counts
- Specific items that changed

**Suggested next workflow** (match on case-sensitive `overallVerdict` token):
- `FEASIBLE` → "Proceed to **[RA] Refine Architecture** to produce an implementation-ready architecture, then **[SS]** to compose your stack skill, then **[TS]** to test and **[EX]** to export."
- `CONDITIONALLY_FEASIBLE` → "Address the {recommendationCount} recommendations above, then re-run **[VS]**. Once all clear, proceed to **[RA]**."
- `NOT_FEASIBLE` → "Critical blockers must be resolved before proceeding. Apply the recommendations above and re-run **[VS]**."

### 5. Append to Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:report`.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Recommendations** and **Evidence Sources** sections to `{outputFile}` (per the fixed heading order in `{feasibilitySchemaRef}`):
- Include overall verdict with rationale in the `## Executive Summary` section (replace the placeholder text from the template)
- Include prioritized recommendation list under `## Recommendations`
- Include delta from previous run (if applicable) under `## Recommendations` as a subsection
- Include suggested next workflow at the end of `## Recommendations`
- Populate `## Evidence Sources`: the template already holds its table, with the header `| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |`. Fill it in place with one row per skill in `skill_inventory` (`{inventoryFile}`: `name`, `evidence_tier`, `confidence_tier` or `none`, `metadata_schema_version` or `none`, and `{skills_output_folder}/{path}/SKILL.md`); the next run's delta reads its `evidence_tier` column (section 3). Below it, list the stack manifest, if any, and the architecture and PRD document paths.
- Update frontmatter (shared-schema keys):
  - Append `'synthesize'` to `stepsCompleted`
  - Set `overallVerdict` to one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE`, `NOT_FEASIBLE` (case-sensitive, underscores not spaces)
  - Set `recommendationCount` to the §1 rollup's `recommendationCount`
  - If delta was computed (section 3), set `deltaImproved`, `deltaRegressed`, `deltaNew`, `deltaUnchanged` from the delta helper's `improvedCount` / `regressedCount` / `newCount` / `unchangedCount`
  - Leave the pair and requirement counts as their stages' tallies wrote them: the report file is the system of record
- Write the `overallVerdict` the §1 rollup returned, verbatim.
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}`. On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `synthesize:report`, with `"path": "{outputFile}"`.

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.


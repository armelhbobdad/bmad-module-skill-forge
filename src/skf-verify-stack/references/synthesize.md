---
nextStepFile: 'report.md'
verdictRollupScript: 'scripts/skf-verdict-rollup.py'
reportDeltaScript: 'scripts/skf-report-delta.py'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
reportUpdateScript: 'scripts/skf-report-update.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
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

**The verdict token is deterministic: do not walk the ladder in prose.** All three passes have already persisted their counts in the `{outputFile}` frontmatter, each from its tally helper, so the script reads them from the report itself:

```bash
uv run {verdictRollupScript} --report "{outputFile}" > "{run_dir}/rollup.json"
```

`--report` reads `coverageCovered`, `coverageMissing` and the other counts steps 2 to 4 persisted, once `stepsCompleted` lists `coverage`, `integrations` and `requirements`; `uv run {verdictRollupScript} --help` gives each key, the input it fills and the ladder. `{run_dir}/rollup.json` holds `overallVerdict` (one of `FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`), `matchedConditions` (the condition codes that fired), `zeroPairsGuardFired`, `recommendations` (how many recommendations of each kind section 2 writes) and `recommendationCount` (their sum). Branch on its exit code and its JSON `code`:

- `HELPER_MISSING` (exit 1): the shared report reader it loads is not installed; HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:rollup`.
- `INVALID_REPORT` or `INVALID_INPUT` (exit 2): its `error` names a stage `stepsCompleted` does not list, a count a stage left out of the frontmatter, a pair count the canonical verdict table does not hold, or counts that disagree; HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `synthesize:rollup`, naming that `error`.
- Any other non-zero exit (no JSON in `{run_dir}/rollup.json`): HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:rollup` with its stderr.

**Write the rationale** from `matchedConditions`, naming the specific findings behind each code:
- `zero-coverage` → "no coverage, analysis vacuous: zero generated skills match the architecture's referenced technologies, so integration and requirements verdicts cannot produce meaningful evidence." Then proceed directly to section 2 to generate recommendations for the Missing and/or Replaced technologies surfaced by Step 02.
- `blocked-integration` → a blocked integration is a fundamental architectural incompatibility; name each Blocked pair and note any co-occurring `missing-coverage`/`risky-integration` codes so the user sees the full set of problems.
- `missing-coverage` / `risky-integration` / `requirements-not-addressed` / `requirements-partial` / `plausible-cap` → the stack can work but has gaps, risks, or unverified assumptions that must be addressed; name the specific items behind each code.
- `zero-integration-pairs` (whatever the verdict) → append: "No integration pair between two covered technologies was found in the architecture document prose, so no integration was verified. Relationships drawn only in diagrams, or implied without an explicit co-mention, are not checked: describe them in prose to have them verified."
- No codes (`FEASIBLE`) → the stack can support the architecture as described: every live technology has a skill, every integration pair is `Verified` (at least one of its two skills cites the other literally), and {IF requirements pass completed:} every requirement is fulfilled {IF requirements pass was skipped:} requirements were not evaluated ({IF `prdDoc` names a path, not `none`:}the PRD at `<prdDoc>` was not found{ELSE:}no PRD provided{END IF}). {IF `pairsVerified` is 0:} The architecture names a single live technology, so it has no integration pair to verify.

### 2. Generate Prescriptive Recommendations

For each non-verified finding across all passes, generate one actionable next step: exactly the number of each kind the §1 rollup's `recommendations` gives (one per Blocked, Missing, Replaced, Risky and Plausible item, one for the zero-pairs note, and one per Not Addressed or Partially Fulfilled requirement when the requirements pass ran), so the list matches the `recommendationCount` the report and the envelope carry:

**Missing skill (from Step 02):**
- "Run **[CS] Create Skill** or **[QS] Quick Skill** for `{library_name}`, then re-run **[VS]** to verify coverage."

**Replaced / being-removed technology (from Step 02):**
- "`{library_name}` is marked for removal/replacement in the architecture document — no skill is needed. Remove it from the architecture document (or, if it is in fact staying, correct the document to drop the removal marker), then re-run **[VS]**."
- Do not emit a [CS]/[QS] recommendation for a Replaced technology — forging a skill for a technology that is being deleted is exactly the misfire this category prevents.

**Risky integration (from Step 03):**
- If a protocol, type or language gap → name the specific bridge for `{lib_a}` ↔ `{lib_b}`: one already in the stack (Tauri's JS↔Rust IPC, say), else a named library, codec or adapter that closes the gap, and where the architecture document records it, or must add it. If no bridge can be named, write "No named bridge identified: manual research required" and one sentence on the selection criteria the user should apply.
- If circular dependency (a step 3 cycle row: `cycle` in its `lib_a`, the chain in its `lib_b`) → "`{A → B → C → A}` form a circular integration dependency: each skill's SKILL.md cites the next. Check that the architecture gives the calls between them one direction, or place an adapter between them, before you build on it."
- If a skill changed mid-run (the rationale "skill modified mid-run") → "`{skill}` changed while this run read it, so `{lib_a}` ↔ `{lib_b}` was not rated: re-run **[VS]**."
- If a skill's API surface could not be read (the rationale "API surface unreadable") → "`{skill}`'s SKILL.md could not be read into an API summary, even on a second read, so `{lib_a}` ↔ `{lib_b}` was not rated: re-run **[VS]**."

**Plausible integration (from Step 03; neither skill cites the other):**
- "Neither `{lib_a}`'s nor `{lib_b}`'s SKILL.md names the other, so the pair stays `Plausible` until one of them does. When a page documents how the two work together (a `{lib_a}` guide that uses `{lib_b}`, say), add it to that skill's brief as a `doc_urls` entry with **[BS] Brief Skill**, re-create the skill with **[CS] Create Skill**, then re-run **[VS]**. Until then, prototype the integration before you rely on it."

**Blocked integration (from Step 03):**
- Name a replacement for `{blocked_lib}` (whichever of the pair's two libraries gives way) or the bridge that lets it work with `{other_lib}`, and the integration path the architecture document must change; a replacement follows the Named-candidate requirement below, and a bridge is named as the Risky line above names one.
- **Named-candidate requirement:** For every Blocked integration where the recommendation proposes replacement, propose AT LEAST ONE named alternative library with a one-line justification (e.g., "Consider `{candidate_name}` — same domain as `{blocked_lib}`, native {target_language} support, compatible with `{other_lib}` via {mechanism}."). If you cannot name at least one concrete candidate, state explicitly: "No named candidate identified — manual research required" and still include one sentence on the selection criteria the user should apply. A Blocked recommendation without either a named candidate or the explicit no-candidate notice is a schema violation.

**Not Addressed requirement (from Step 04):**
- "No library in the stack covers `{requirement}`. Evaluate `{category}` libraries that provide this capability, generate a skill, then re-run **[VS]**."

**Partially Fulfilled requirement (from Step 04):**
- "Gap in `{requirement}`: {what_is_missing}. Consider extending `{contributing_skill}` or adding a dedicated library."

**Zero integration pairs (from Step 03):**
- When `matchedConditions` holds `zero-integration-pairs` (no pair across two or more covered technologies): "No integration claims were found in the architecture document prose. Add explicit prose descriptions of how your technologies interact (not only in diagrams), then re-run **[VS]** to verify integrations."

### 3. Check for Previous Report

Read `previousReport` from `{outputFile}` frontmatter (set in step 1): an earlier run's report, or empty when there is none or the user skipped the comparison. Step 1 compares against the newest earlier report unless the user names another; to compare against an older run, pass its timestamped report in step 1.

**If `previousReport` is set:** the delta helper reads both reports itself: the Coverage Analysis rows and the canonical `| lib_a | lib_b | verdict | rationale |` table of each, and the `evidence_tier` column of the previous report's `## Evidence Sources` table (section 5 writes it). It reads this run's tiers, each skill's `evidence_tier`, from `{inventoryFile}`. Run:

```bash
uv run {reportDeltaScript} --previous-report "{previousReport}" --current-report "{outputFile}" --inventory "{inventoryFile}" > "{run_dir}/delta.json"
```

`{run_dir}/delta.json` (run `uv run {reportDeltaScript} --help` for the contract and rankings) holds `improved`/`regressed`/`unchanged`/`new`/`dropped`/`replaced` label lists with counts, `tierDowngrades` (each `{skill, from, to}`: a drop along `T1` > `T1-low` > `T2` > `T3`, such as `T1` to `T1-low`, counts as a regression) and `previousTiersRecorded`. Branch on its exit code and its JSON `code`:

- Exit 0: render the delta section from those results. When `previousTiersRecorded` is false (a report written before tiers were recorded), add "The previous report records no skill tiers, so tier changes were not compared." For each tier downgrade, flag: "skill `{skill}` evidence fell from `{from}` to `{to}`: check the forge tier with [SF] Setup Forge, then re-create the skill at its earlier tier with [CS] ([SS] for a stack skill)".
- `UNKNOWN_TIER` or `INVALID_INPUT` (exit 2): a tier outside the scale, or an `{inventoryFile}` it cannot read. Note its `error`, run it again with `--no-tiers` added before the `>`, render the delta section from that run, and add "Tier changes were not compared: {error}".
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

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the synthesis to `{outputFile}` (per the fixed heading order in `{feasibilitySchemaRef}`), each part to its own file first:
- `{run_dir}/executive-summary.md`: the overall verdict with its rationale, which replaces the template's placeholder text under `## Executive Summary`
- `{run_dir}/recommendations.md`: the prioritized recommendation list; then, when `previousReport` is set, the section 3 delta section (or its "No delta" line) under a `#### Delta from Previous Run` heading; then the suggested next workflow, last
- `{run_dir}/input-documents.md`: the architecture and PRD document paths, a PRD path (not `none`) whose `prdAvailable` is false marked `(not found)`, which go below the Evidence Sources table

The report keeps its `##` headings and the helper writes each `###` line, so no file holds a `#` or `##` heading, and the last two hold no `###` heading either.

Render the rows of the template's `| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |` table from the inventory, one per skill (the next run's delta reads its `evidence_tier` column, section 3):

```bash
uv run {coverageTallyScript} --kind evidence --render --skills-root "{skills_output_folder}" --stdin < "{inventoryFile}" > "{run_dir}/evidence-table.md"
```

On a non-zero exit, `{run_dir}/evidence-table.md` holds a JSON `error` instead, naming a skill the inventory gives no name or path, or an evidence tier off the scale: HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `synthesize:report`, naming that `error`. Then run the calls in order, stopping at the first that exits non-zero:

```bash
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Executive Summary' < "{run_dir}/executive-summary.md"
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Recommendations' --subsection 'Prioritized Recommendations' < "{run_dir}/recommendations.md"
uv run {reportUpdateScript} fill-table --report "{outputFile}" --heading 'Evidence Sources' < "{run_dir}/evidence-table.md"
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Evidence Sources' --subsection 'Input Documents' < "{run_dir}/input-documents.md"
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind delta < "{run_dir}/delta.json"
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind synthesize < "{run_dir}/rollup.json"
```

Skip the `--kind delta` call unless section 3 computed a delta. The last call records the §1 rollup's `overallVerdict` and `recommendationCount` verbatim. On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:report`. On exit 2 with `INVALID_INPUT`, or with no JSON (a usage error), fix the file or the call its `error` or usage line names, then run that call and the ones after it again. On exit 2 with `INVALID_REPORT`, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `synthesize:report`, naming its `error`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `synthesize:report`, with `"path": "{outputFile}"`, naming its JSON `error`.

### 6. Auto-Proceed to Next Step

"**Proceeding to final report presentation...**"

Load, read the full file and then execute `{nextStepFile}`.


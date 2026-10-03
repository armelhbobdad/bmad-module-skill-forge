---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
schemaFile: 'assets/skill-brief-schema.md'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 6: Generate Briefs

## STEP GOAL:

To write a valid skill-brief.yaml for each confirmed unit through the brief writer, append the generation results to the analysis report, recommend the next workflow for each unit and end the run with its result files and envelope, completing the analyze-source workflow (also when no unit was confirmed).

## Rules

- Generate only for units in confirmed_units — no extras, no omissions
- Do not revisit the per-unit decisions of step 5: the §4 preview confirms only the write
- Every generated field must trace back to data collected in steps 02-05
- Briefs are written only by the brief writer, from a context file: never render or hand-edit brief YAML
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is not the terminal step

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one and the envelope fields the site names, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Context

Read {outputFile} completely to obtain:
- `confirmed_units` from frontmatter (names of units approved in step 05)
- `confirmed_composites` from frontmatter (composites approved in step 04, each with its constituents' names and paths)
- `project_paths`, `refs`, `forge_tier`, `user_name`, `forge_data_folder` from frontmatter
- Recommendation cards from "## Recommendations" section (proposed brief fields and the project path of each unit)
- Export map and integration data from prior sections

Load {schemaFile} for validation reference.

**No confirmed unit:** If `confirmed_units` is empty, present:
"**No confirmed units to generate briefs for.** The analysis is complete with no skill briefs produced. Run analyze-source again with different scope or parameters if needed."
The run still ends through the same sequence as one that wrote briefs: skip §2 to §6 and continue at §7, which appends the Generation Results with no brief and adds `generate-briefs` to `stepsCompleted` (so a re-run starts a fresh analysis instead of resuming into this guard), then §8, §9 (an envelope and result contract with `brief_paths: []` and `unit_counts.confirmed: 0`), §9b and §10.

### 2. Build Each Brief's Context

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}` and **`{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `generate-briefs:2`): "`{the missing script}` is missing. Re-install SKF."

The brief writer renders, checks and writes each brief, and applies the version precedence (`target_version`, then `detected_version`, then `1.0.0`): this step supplies the values. For each unit in `confirmed_units`, take them from:

**Field mapping:**

| Field | Source |
|-------|--------|
| name | Confirmed name from step 05 recommendation card: the name identify-units Step C derived, unless step 5 renamed the unit |
| version | Not set here: `detected_version` comes by {schemaFile}'s **Version Detection**, for the unit's own manifest in its project path's manifest scan, `{run_dir}/manifests-{i}.json` (scan-project and discover-additional-source write it). When that file is missing, as in a session that resumed the report, run `uv run {scanManifestsHelper} scan "{scan_root}" > "{run_dir}/manifests-{i}.json"` first, `{scanManifestsHelper}` the first existing path of `{scanManifestsProbeOrder}` |
| source_repo | The unit's project path, the `project_paths[]` entry it was found under (a composite's constituents share one) |
| target_ref | The unit's ref: its project path's entry in `refs`, else null. Never a version: `target_version` stays null |
| language | Language the skill **documents** (primary language detected in step 03). For a language / spec reference this is the *documented* language, which may differ from the source language it is extracted from — e.g. a SurrealQL reference extracted from a Rust engine records `surrealql`, not `rust` (see {schemaFile} "Documented vs source language") |
| scope.type | Scope type from step 05 recommendation card |
| scope.include | Include patterns from step 05 recommendation card, plus, for a composite (`Boundary: Composite` on its card), `<path>/**` for every constituent path of its `confirmed_composites` entry (such as `crates/animato-core/**`), so the brief spans every constituent. Find the entry by those paths, which the card's Path lists, not by name: step 05 may rename the unit |
| scope.exclude | Inferred from heuristics (test files, generated code) |
| scope.tier_a_include | Optional — narrower tier-A surface for stratified-scope monorepos and `reference-app` pattern surfaces; usually left to skf-brief-skill to refine |
| scope.notes | Rationale from step 05 recommendation card |
| description | Description from step 05 recommendation card |
| forge_tier | `{forge_tier}` from frontmatter |
| created | Current date, `YYYY-MM-DD` |
| created_by | `{user_name}` from frontmatter |

Write each unit's context as `{run_dir}/brief-{unit-name}.json`, a file and never an echo'd string:

```json
{
  "name": "{unit-name}",
  "target_version": null,
  "target_ref": "{the unit's ref, or null}",
  "detected_version": "{version, or null}",
  "source_type": "source",
  "source_repo": "{source_repo}",
  "language": "{language}",
  "description": "{description}",
  "forge_tier": "{forge_tier}",
  "created": "{current_date}",
  "created_by": "{user_name}",
  "scope_type": "{scope.type}",
  "scope_include": ["{scope.include}"],
  "scope_exclude": ["{scope.exclude}"],
  "scope_notes": "{scope.notes}",
  "scope_rationale": null,
  "scope_tier_a_include": null,
  "scope_amendments": null,
  "scope_registry_path": null,
  "scope_ui_variants": null,
  "scope_demo_patterns": null,
  "doc_urls": null,
  "scripts_intent": null,
  "assets_intent": null,
  "source_authority": null,
  "source_ref": null
}
```

### 3. Validate Each Brief

Validation has two parts: a **deterministic gate** (authoritative for structure) and **semantic cross-checks** the schema cannot express. Run the gate first.

**3a. Deterministic gate.** Render each brief into the run folder, then run on it the schema check `skf-brief-skill` runs when it reads a brief, so a brief that passes here is not rejected there for structural reasons:

```bash
uv run {writeSkillBriefHelper} write --target "{run_dir}/briefs/{unit-name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{unit-name}.json"
uv run {validateBriefSchemaHelper} "{run_dir}/briefs/{unit-name}/skill-brief.yaml"
```

- **The writer exits non-zero, or the validator answers `valid: false`:** the `message` and `field` of the writer's stderr JSON, or the validator's `errors[]`, name the offending field. Correct that value in `{run_dir}/brief-{unit-name}.json` when it is a value you mistyped from the recommendation card, and run both commands again; a value the user must decide is presented in §4 for correction (`M`). In headless mode a brief still rejected after one correction is a HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:3`, path `{forge_data_folder}/{unit-name}/skill-brief.yaml`, with `unit_counts` from step 5): "The brief for {unit-name} was rejected: {the message}." A brief is written only after it passes this gate.
- **Both pass:** carry the writer's and the validator's non-empty `warnings` into the §4 preview, then proceed.

**3b. Semantic cross-checks** (not expressible in the JSON schema — apply in addition to 3a):

1. **Name uniqueness** — no duplicate names within the batch or existing skills
2. **Source accessible** — project_path exists
3. **Language recognized** — valid programming language identifier
4. **Forge tier match** — matches forge_tier from config

(The non-empty `scope.include` constraint — at least one glob pattern for every scope type except `docs-only` — is enforced deterministically by the §3a gate, so it is not re-checked here.)

**If any check fails:**
- Document the failure with specific field and reason
- Correct the context (3a) or present to user for correction (3b semantic issues) before writing: an invalid brief is not written
- In headless mode no one corrects it: correct what the recommendation card and the report settle and check again, once; a brief still failing a 3b check is a HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:3`, path `{forge_data_folder}/{unit-name}/skill-brief.yaml`, with `unit_counts` from step 5), as in 3a: "The brief for {unit-name} failed the {check} check: {the reason}."

### 4. Present Generation Preview

"**Skill Brief Generation Preview**

**Units to generate:** {count}

{For each unit:}
---
**{unit-name}** → `{forge_data_folder}/{unit-name}/skill-brief.yaml`{, replacing the earlier brief there when the unit is in `existing_briefs`}
```yaml
{the content of {run_dir}/briefs/{unit-name}/skill-brief.yaml, as the writer rendered it}
```
---

**Validation:** {all passed / N issues found}
{List any validation issues}

**Ready to write {count} skill-brief.yaml files.** Confirm to proceed? (Y to write all briefs / N to skip writing but continue to report update / M to modify a specific brief / X to cancel and exit the workflow)"

Wait for explicit user confirmation before writing files.

**GATE [default: Y]**: if `{headless_mode}` is true, auto-confirm [Y] and write all briefs, and record that decision the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "generate-briefs.write", "default_action": "Y", "taken_action": "Y", "reason": "headless: auto-write {count} briefs", "evidence": {"briefs": [<each unit name>]}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost. Do not stall at this gate: it is the deliverable-producing step of a headless or pipeline run.

### 5. Write Files

**IF user confirms (Y):**

Write each brief to its place from the context that passed §3 (the writer renders the same bytes the preview showed, creates the folder and writes atomically):

```bash
uv run {writeSkillBriefHelper} write --target "{forge_data_folder}/{unit-name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{unit-name}.json"
```

Keep each `brief_path` it prints for §9. If it exits non-zero, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:5`, path `{forge_data_folder}/{unit-name}/skill-brief.yaml`, with `unit_counts` from step 5 and the `brief_paths` written so far): "The brief for {unit-name} could not be written: {its `message`}."

**IF user modifies (M):**
- Ask which brief and what to change
- Update `{run_dir}/brief-{unit-name}.json`, run the §3 gate again, present again
- Return to confirmation prompt

**IF user skips writing (N):**
- Document the skip decision
- Skip file writing, proceed to report update

**IF user cancels (X):**
- HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `generate-briefs:4`), with `brief_paths: []` and `unit_counts` reflecting the confirmed/skipped/maybe state from step 5 in its payload: "Cancelled before any brief was written."

### 6. Determine Next Workflow Per Unit

For each generated brief, recommend the appropriate next workflow:

| Condition | Recommendation |
|-----------|---------------|
| Brief has `scope.type: full-library` and unit is well-bounded | create-skill — brief is sufficient for direct skill creation |
| Brief has `scope.type: component-library` and registry defines boundaries | create-skill — component boundaries defined by registry |
| Brief has `scope.type: specific-modules` or scope needs refinement | brief-skill — refine scope before creating skill |
| Brief has `scope.type: public-api` or complex interface | brief-skill — detailed scoping needed |
| Brief has `scope.type: reference-app` | brief-skill — refine the pattern surface and capture `tier_a_include` before creating skill |
| Unit flagged as stack skill candidate | create-stack-skill — after individual skills exist |
| Unit flagged as already-skilled | update-skill — refresh existing skill |

### 7. Append to Report

Append the complete "## Generation Results" section to {outputFile}:

Replace `[Appended by generate-briefs]` with:

**Generated Briefs:**
| # | Unit Name | Output Path | Validation | Next Workflow |
|---|-----------|-------------|------------|---------------|
| {n} | {name} | {path} | {pass/fail} | {recommendation} |

**Generation Summary:**
- Total confirmed units: {count}
- Briefs generated: {count}
- Briefs skipped/failed: {count}
- Stack skill candidates flagged: {count}

**Next Steps:**
{For each next workflow recommendation, a clear action item}

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'generate-briefs' to existing array]
lastStep: 'generate-briefs'
nextWorkflow: '{primary recommendation}'
```

### 8. Present Summary

"**Analyze-Source Summary**

**Project:** {project_name}
**Forge Tier:** {forge_tier}

**Results:**
- **Scanned:** {boundary count} boundaries detected
- **Identified:** {unit count} qualifying units classified
- **Confirmed:** {confirmed count} units approved for brief generation
- **Generated:** {brief count} skill-brief.yaml files written

**Files Created:**
{List each skill-brief.yaml with full path}

**Analysis Report:** {outputFile}

**Recommended Next Steps:**
{For each unit, the recommended next workflow with brief explanation}

{If stack skill candidates exist:}
**Stack Skill Candidates:**
{List candidates with recommendation to run create-stack-skill after individual skills are created}

To refine any brief, run the recommended next workflow. To re-analyze with different scope, run analyze-source again."

### 9. End the Run

The shared emitter writes the result files and prints the envelope; this section stages their content, in every mode. Write `{run_dir}/result-context.json`:

```json
{
  "status": "success",
  "report_path": "{outputFile as an absolute path}",
  "brief_paths": ["{the brief_path of each brief §5 wrote}"],
  "unit_counts": {"confirmed": <confirmed count from step 5>, "skipped": <rejected count from step 5>, "maybe": 0},
  "mode": "interactive",
  "result_contract": {
    "skill": "skf-analyze-source",
    "status": "success",
    "outputs": [{"type": "report", "path": "{outputFile as an absolute path}"}, {"type": "brief", "path": "{each brief_path}"}],
    "summary": {"mode": "interactive", "brief_count": <briefs written>, "confirmed_units": <confirmed count>, "stack_skill_candidates": <count>, "next_workflow": "{primary recommendation}"}
  }
}
```

`brief_paths` is empty, and so is the brief part of `outputs`, when no unit was confirmed or the user skipped writing with [N]. Then run:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-analyze-source --run-dir "{run_dir}" --result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"
```

The emitter stamps the UTC time and the run id into the record, writes `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` and its `analyze-source-result-latest.json` copy (the stable path pipeline consumers read), and prints the `SKF_ANALYZE_RESULT_JSON:` line on stdout (field rules in `references/headless-contract.md`). When `{headless_mode}` is true, display the line verbatim: it is the success signal of a headless run. A result file that could not be written leaves the line's `result_path` null and a `result_file_write_failed` warning in it, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:9`, path `{forge_data_folder}`, with `brief_paths` and `unit_counts` from the payload): "The result contract could not be written: {its message}."

### 9b. On-Complete Hook (pipeline integration)

If `{onCompleteCommand}` is non-empty and the §9 line's `result_path` is not null, invoke it now, after the emitter wrote the timestamped result JSON and its `analyze-source-result-latest.json` copy:

```
{onCompleteCommand} --result-path={forge_data_folder}/analyze-source-result-latest.json
```

The stable `-latest` path is preferred over the timestamped copy so downstream consumers don't need to discover the timestamp.

- On success: display the hook's stderr, if it wrote any, as information (`on_complete hook stderr: …`).
- On non-zero exit / process error: display the hook failure (`on_complete hook failed (exit {code}): {stderr_snippet}`); it never fails the run.
- **Never fail the workflow on hook errors** — the hook is for pipeline integration (Slack, dashboards, CI), not for gating skill-brief production.

If `{onCompleteCommand}` is empty, skip this section entirely (default behavior — no hook configured).

### 10. Chain to Health Check

After the briefs are written (or skipped, or none was confirmed), the report updated, the summary presented, the run ended in §9 and the on-complete hook invoked (or skipped per empty `{onCompleteCommand}`), delete the run folder, whose payloads the emitter has read: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step: continue past the summary even though it reads as final.

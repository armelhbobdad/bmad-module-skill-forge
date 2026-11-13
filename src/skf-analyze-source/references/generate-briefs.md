---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
schemaFile: 'assets/skill-brief-schema.md'
scanRootFile: 'references/scan-root.md'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
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
- `project_paths`, `scan_roots` (each project path's scan root), `refs`, `forge_tier`, `existing_skills`, `user_name`, `forge_data_folder` from frontmatter
- Recommendation cards from "## Recommendations" section (proposed brief fields and the project path of each unit)
- Export map and integration data from prior sections

Read {schemaFile}'s **Version Detection** section only when a unit's own manifest in its scan is `version_dynamic` or a private workspace root without a `version`: the scan's `version` of any other manifest is passed as found.

**No confirmed unit:** If `confirmed_units` is empty, present:
"**No confirmed units to generate briefs for.** The analysis produced no skill briefs. Run analyze-source again with different scope or parameters if needed."
The run still ends through the same sequence as one that wrote briefs: skip §2 to §6 and continue at §7, which appends the Generation Results with no brief and adds `generate-briefs` to `stepsCompleted` (so a re-run starts a fresh analysis instead of resuming into this guard), then §8, §9 (an envelope and result contract with `brief_paths: []` and `unit_counts.confirmed: 0`), §9b and §10.

### 2. Build Each Brief's Context

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`, **`{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}` and **`{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `generate-briefs:2`): "`{the missing script}` is missing. Re-install SKF."

**A scan root that is gone.** A session that resumed this report without its earlier run folder works in a new one, without the copies that folder held. For each project path a confirmed unit was found under whose recorded scan root no longer exists, make it again by {scanRootFile} into this run's `{run_dir}/source-{i}` and update `scan_roots` in {outputFile}'s frontmatter: §3b checks each brief's `source_repo` against it, and the version row below scans it when its `{run_dir}/manifests-{i}.json` is missing. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `generate-briefs:2`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

The brief writer renders, checks and writes each brief, and applies the version precedence (`target_version`, then `detected_version`, then `1.0.0`): this step supplies the values. For each unit in `confirmed_units`, take them from:

**Field mapping:**

| Field | Source |
|-------|--------|
| name | Confirmed name from step 05 recommendation card: the name identify-units Step C derived, unless step 5 renamed the unit |
| version | Not set here: `detected_version` comes by {schemaFile}'s **Version Detection**, for the unit's own manifest in its project path's manifest scan, `{run_dir}/manifests-{i}.json` (scan-project and discover-additional-source write it). When that file is missing, as in a session that resumed the report without its earlier run folder, run `uv run {scanManifestsHelper} scan "{scan_root}" > "{run_dir}/manifests-{i}.json"` first, `{scanManifestsHelper}` the first existing path of `{scanManifestsProbeOrder}` |
| source_repo | The unit's project path, the `project_paths[]` entry it was found under (a composite's constituents share one) |
| target_ref | The unit's ref: its project path's entry in `refs`, else null. Never a version: `target_version` stays null |
| language | Language the skill **documents** (primary language detected in step 03). For a language / spec reference this is the *documented* language, which may differ from the source language it is extracted from — e.g. a SurrealQL reference extracted from a Rust engine records `surrealql`, not `rust` (see {schemaFile} "Documented vs source language") |
| scope.type | Scope type from step 05 recommendation card |
| scope.include | The `scope.include` patterns of the step 05 recommendation card (a composite's, the union of its constituents', so the brief spans every constituent) |
| scope.exclude | The `scope.exclude` patterns of the step 05 recommendation card |
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
  "scope_notes": "{scope.notes}"
}
```

Leave out every other optional key: the writer reads an absent key as unset.

### 3. Validate Each Brief

Validation has two parts: a **deterministic gate** on each brief (§3a), then a **batch check** across them (§3b). Run the gate first.

**3a. Deterministic gate.** Render each brief into the run folder, then run on it the schema check `skf-brief-skill` runs when it reads a brief, so a brief that passes here is not rejected there for structural reasons:

```bash
uv run {writeSkillBriefHelper} write --target "{run_dir}/briefs/{unit-name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{unit-name}.json"
uv run {validateBriefSchemaHelper} "{run_dir}/briefs/{unit-name}/skill-brief.yaml"
```

- **The writer exits non-zero, or the validator answers `valid: false`:** the `message` and `field` of the writer's stderr JSON, or the validator's `errors[]`, name the offending field. Correct that value in `{run_dir}/brief-{unit-name}.json` when it is a value you mistyped from the recommendation card, and run both commands again; a value the user must decide is presented in §4 for correction (`M`). In headless mode a brief still rejected after one correction is a HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:3`, path `{forge_data_folder}/{unit-name}/skill-brief.yaml`, with `unit_counts` from step 5): "The brief for {unit-name} was rejected: {the message}." A brief is written only after it passes this gate.
- **Both pass:** carry the writer's and the validator's non-empty `warnings` into the §4 preview, then proceed.

**3b. Batch checks.** When every brief passed §3a, check them together, for a name another brief or `existing_skills` has (a step 5 rename can collide) and a `source_repo` that is neither an existing folder nor a project path whose scan root exists:

```bash
uv run {validateBriefSchemaHelper} batch --contexts "{run_dir}"/brief-*.json --existing-skills <each existing_skills name> --project-paths <each project_paths entry, quoted> --scan-roots <the scan_roots entry of each, quoted, in the same order>
```

Its `errors[]` have §3a's shape and are 3b failures: each names its `context` file, and its brief `name`, `field` and `message` are the {unit-name}, {check} and reason below. An exit 2 is a call it could not check, named on its stderr: correct the call and run it again; a second exit 2 counts as a failed `batch` check of the first unit in `confirmed_units`, its reason the first stderr line.

**If any check fails:**
- Document the failure with specific field and reason
- Correct the context (3a) or present to user for correction (3b issues) before writing: an invalid brief is not written
- In headless mode no one corrects it: correct what the recommendation card and the report settle and check again, once; a brief still failing a 3b check is a HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:3`, path `{forge_data_folder}/{unit-name}/skill-brief.yaml`, with `unit_counts` from step 5), as in 3a: "The brief for {unit-name} failed the {check} check: {the reason}."

### 4. Present Generation Preview

"**Skill Brief Generation Preview**

**Units to generate:** {count}

{For each unit:}
---
**{unit-name}** → `{forge_data_folder}/{unit-name}/skill-brief.yaml`{, replacing the earlier brief there when the unit is in `existing_briefs`}{, its version read from `{version_source}` when Version Detection's extractor call found the `version` the brief shows}
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
- Update `{run_dir}/brief-{unit-name}.json`, run §3a on it and §3b again (a rename can collide), present again
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

Tell the user each brief written (or that none was), with its path and its unit's §6 next workflow, the analysis report's path ({outputFile}), and the §6 stack skill candidates, if any, with create-stack-skill to run once their skills exist.

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

The emitter stamps the UTC time and the run id into the record, writes `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` and its `analyze-source-result-latest.json` copy (the record of the last run whose emitter wrote this copy, at a stable path; a caller reads its own run's `SKF_ANALYZE_RESULT_JSON` line), and prints the `SKF_ANALYZE_RESULT_JSON:` line on stdout (field rules in `references/headless-contract.md`). When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here: the shared health check displays it verbatim as the run's last line (the line the retry below prints when the first run printed none, and empty when neither run printed one). A per-run record that could not be written leaves `result_path` null, and a `-latest` copy that could not be written leaves it set; either adds a `result_file_write_failed` warning to the line, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:9`, path `{forge_data_folder}`, with `brief_paths` and `unit_counts` from the payload): "The result contract could not be written: {its message}."

### 9b. On-Complete Hook (pipeline integration)

If `{onCompleteCommand}` is non-empty, the §9 line's `result_path` is not null and its `warnings` hold no `result_file_write_failed` entry naming `analyze-source-result-latest.json`, invoke it now from `{project-root}`: `{onCompleteCommand} --result-path="{forge_data_folder}/analyze-source-result-latest.json"`. Display a hook failure; it never fails the run. When `{onCompleteCommand}` is non-empty but `result_path` is null or a `result_file_write_failed` warning names `analyze-source-result-latest.json` (the copy alone failed), skip the hook and say so: "on_complete skipped: `analyze-source-result-latest.json` was not written."

### 10. Chain to Health Check

Delete the run folder, whose payloads the emitter has read: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`, the run's terminal step, so continue past the summary.

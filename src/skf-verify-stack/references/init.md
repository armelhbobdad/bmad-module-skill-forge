---
nextStepFile: 'coverage.md'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
# The skill inventory §2 writes and every later stage reads from disk, in the
# run folder the pre-flight creates.
inventoryFile: '{run_dir}/skill-inventory.json'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
# Resolve `{enumerateStackSkillsHelper}` by probing
# `{enumerateStackSkillsProbeOrder}` in order (installed SKF module path
# first, src/ dev-checkout fallback); first existing path wins. §2 calls
# it for the deterministic inventory of the skills SKF generated
# (cascade-resolved exports, metadata-hash for change-detection, the
# exports-source confidence, the evidence tier, and `not_skf_output` for
# the rest). If neither candidate exists, §2 halts (resolution-failure).
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
# The shared feasibility-report helper holds the slug rule every consumer
# of this report applies; the section before §1 binds `{project_slug}` from it.
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
previousReportScript: 'scripts/skf-previous-report.py'
---

<!-- Config: communicate in {communication_language}. Initialize the feasibility report skeleton in {document_output_language}. -->

# Step 1: Initialize Verification

## STEP GOAL:

Load all generated skills from the skills output folder, accept the architecture document path (required) and optional PRD/vision document path from the user, validate that all inputs exist and are readable, create the feasibility report document, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and creating the report skeleton — do not perform analysis
- Auto-proceed — halts only on validation errors

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"report_path": "{outputFile}"` once §4 wrote the report and `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Pre-flight: run folder and write probe.** Both run before the first prompt. Create the run folder:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
```

If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." With no folder to stage in, a headless run passes the payload to the emitter directly:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --target stderr <<'SKF_VS_HALT'
{"phase": "init:run-folder", "reason": "<the halt message>", "halt_reason": "write-failed"}
SKF_VS_HALT
```

Then verify `{outputFolderPath}` is writable: a read-only mount, full disk, or permissions-denied path otherwise only surfaces at §4's atomic write, after the user has gone through the input prompts.

```bash
mkdir -p "{outputFolderPath}" && \
  printf 'probe' > "{outputFolderPath}/.skf-write-probe" && \
  rm "{outputFolderPath}/.skf-write-probe"
```

On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:write-probe`, with `"path": "{outputFolderPath}"`.

**Bind `{project_slug}`.** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins. Run:

```bash
uv run {validateFeasibilityReportHelper} --locate "{outputFolderPath}" --project-name "{project_name}"
```

Bind `{project_slug}` ← `projectSlug`, whatever `status` says: this run needs only the slug, and the helper holds the one slug rule that the consumers of this report apply when they look for it. If no candidate exists, or the command prints no JSON: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:project-slug`.

### 1. Accept Input Documents

"**Verify Stack — Feasibility Analysis** (read-only — never modifies your skills, architecture doc, or PRD).

If you meant to *generate* skills first, type `cancel` and run `[CS] Create Skill` or `[QS] Quick Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc
2. **PRD or vision document path** (OPTIONAL) — for requirements coverage analysis
3. **Previous feasibility report path** (OPTIONAL): a timestamped report from an earlier run, for delta comparison. Leave it empty to compare against the most recent one found.

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

Wait for user input. **GATE [default: use args]**: if `{headless_mode}` and `--architecture-doc` was provided, use that path and auto-proceed, log: "headless: using provided architecture path". If `--prd` and/or `--previous-report` were provided, consume them at the corresponding sub-validations below. If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) at phase `init:input-documents`.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt below: Display "Cancelled — no analysis was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable → "Architecture document not found at `{path}`. Provide a valid path."
- HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:architecture-doc`, with `"path"` set to the path given, if the user cannot provide a valid path; a headless run has no one to ask, so it halts at once.

**Validate PRD document (if provided):**
- Confirm the file exists and is readable
- If missing → "PRD document not found at `{path}`. Proceeding without PRD — requirements pass will be skipped."
- Store PRD availability as `prdAvailable: true|false`

**Resolve the previous report.** Run the previous-report helper, with `--provided` set to the path when `--previous-report` or the prompt gave one, and without it otherwise:

```bash
uv run {previousReportScript} --folder "{outputFolderPath}" --slug "{project_slug}" --timestamp "{timestamp}" [--provided "<path>"]
```

It never returns a file this run writes (`{outputFile}` or `{outputFileLatest}`); without `--provided` it picks the newest earlier report that finished. When it prints no JSON (exit 2, a usage error), the line it prints names the flag it rejected: fix that flag's value and run it again. Otherwise branch on `status`:

- `collision` (exit 1): "`{provided}` is `{collidesWith}`, which this run overwrites. Give a timestamped report from an earlier run, or leave the path empty to compare against the most recent one." Interactive: wait for the answer, run the helper again with `--provided` set to it (or without `--provided` for an empty answer), and branch on its `status` as here. In headless, where the path came from `--previous-report`: HALT (exit code 5, `halt_reason: "previous-report-collision"`) at phase `init:previous-report`, with `"path"` set to the path given.
- `not-found`: "Previous report not found at `{provided}`. Proceeding without delta comparison." Set `previousReport` to empty.
- `provided`: set `previousReport` to the returned `previousReport`.
- `discovered` (no path was given): interactive, offer "Found a prior report from `{previousTimestamp}`: compare against it? **[Y]** use it / paste a different path / **[skip]** / **[X]** cancel". On [Y], set `previousReport` to the returned `previousReport`; on a pasted path, run the helper again with `--provided` set to it and branch on its `status` as above; on `skip`, leave `previousReport` empty; on [X], cancel as above (exit code 6).
  **GATE [default: Y]**: if `{headless_mode}`, set `previousReport` to the returned `previousReport`, log: "headless: delta comparison against `{previousReport}`", and record the decision in the run sink the moment it is taken. Stage `{run_dir}/decision.json` as `{"gate": "init.previous-report", "default_action": "Y", "taken_action": "Y", "reason": "headless: delta comparison against <previousReport>", "evidence": {"previous_report": "<previousReport>"}}` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-verify-stack --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- `none`: leave `previousReport` empty (no finished earlier report, no delta).
- `reader-missing` (exit 3): the shared report reader the helper loads is not installed: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:previous-report`, naming the file its `error` gives.

### 2. Scan Skills Folder

**Pre-flight: skills folder existence.**
- If `{skills_output_folder}` does not exist on disk: HALT (exit code 3, `halt_reason: "skills-folder-missing"`) at phase `init:skills-folder` with "**Cannot proceed.** `{skills_output_folder}` does not exist: run **[SF] Setup Forge** to initialize the forge, then generate skills with [CS] or [QS]."
- If `{skills_output_folder}` exists but is empty (no subdirectories at all): HALT (exit code 3, `halt_reason: "skills-folder-missing"`) at phase `init:skills-folder` with "**Cannot proceed.** `{skills_output_folder}` contains 0 skills. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]."

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`.

**Enumerate the skills with the shared helper:**

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability > "{inventoryFile}"
```

If the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`, naming its first stderr line. Read `{inventoryFile}` now: every later stage reads the inventory from it, not from context.

The helper reads only the skills SKF generated (its `--help` says how it picks each package and resolves its exports). The later stages read these fields of each `skills[]` entry: `name` (the folder name), `path` (the package, relative to `{skills_output_folder}`), `exports`, `exports_source`, `confidence` (from the exports source, not metadata's `confidence_tier`), `evidence_tier` (`T1`, `T1-low`, `T2` or `T3`, one scale for every skill type), `confidence_tier`, `metadata_schema_version`, `language` (a string, or a list for a stack), `exports_documented`, `source_repo_basename` and `source_root_basename`, so no stage opens `metadata.json`. `warnings[]` names per-skill problems, each starting `<name>: `. The file is `skill_inventory` (used by §3, §4, §5, the coverage and integrations stages, and synthesize's delta and Evidence Sources table), and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count` and `{inventory_warnings}` ← `warnings`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders, such as a module's own skills in a shared skills folder, are not in `skills[]` and count toward neither `{skill_count}` nor `{warning_count}`.

`--reliability` adds `inventory_reliable` (bool), `unreliable_ratio` (float), `skill_count` and `warning_count`, over the skills SKF generated and their warnings.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `init:inventory` with: "Inventory scan unreliable: {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [VS]." The helper's threshold is chosen so a single malformed skill in a small 3-5 skill inventory does not trip the halt.

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 2 skills SKF generated must exist (`{skill_count}`; a stack requires multiple libraries)
- If fewer than 2 → "**Cannot proceed.** Only {skill_count} skill(s) SKF generated were found in `{skills_output_folder}`. A stack requires at least 2 skills. Generate more skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]." When `{not_skf_output}` is non-empty, append: "Skipped (not SKF output): {not_skf_output}."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`) at phase `init:skill-count`.

**Check forge_data_folder:**
- Verify `forge_data_folder` was resolved from config.yaml and is non-empty
- If undefined or empty → "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Re-run [SF] Setup Forge to initialize."
- HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `init:forge-data-folder`.

### 4. Create Feasibility Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report`.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report`.

This skill produces the feasibility report schema defined in `{feasibilitySchemaRef}`; every output conforms to that schema — `schemaVersion: "1.0"`, the verdict token set (`Verified|Plausible|Risky|Blocked`; overall `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE`), the filename pattern, and the section-heading order.

**Filename variables:** `timestamp` was fixed at activation (SKILL.md On Activation §2) and `project_slug` by the Bind block at the top of this step; reuse them, do not re-derive. `{outputFile}` and `{outputFileLatest}` resolve from them per the stage frontmatter template, the latter as a copy, not a symlink (per schema), which only report.md §1 writes.

**Load** `{reportTemplatePath}` (the customize-aware template path resolved in SKILL.md On Activation §4) and stage the initial content. Substitute the template's `Schema contract:` line `{feasibilitySchemaRef}` placeholder with the resolved schema path so every emitted report cites a path that exists on the running machine.

**Populate frontmatter (per shared schema — required keys):**
- `schemaVersion: "1.0"`
- `reportType: feasibility`
- `projectName: "{project_name}"`
- `projectSlug: "{project_slug}"`
- `generatedAt: "{ISO-8601 UTC}"`
- `generatedBy: skf-verify-stack`
- `overallVerdict: "CONDITIONALLY_FEASIBLE"` (provisional until step 5 finalizes)
- `coveragePercentage: 0`
- `pairsVerified: 0`, `pairsPlausible: 0`, `pairsRisky: 0`, `pairsBlocked: 0`
- `recommendationCount: 0`
- `prdAvailable: true|false` (from section 1 validation)

**Populate producer-local bookkeeping keys (not part of the consumer contract):**
- `architectureDoc`, `prdDoc` (or "none"), `previousReport` (or empty string)
- `skillsAnalyzed: {skill_count}`
- `stepsCompleted: ['init']`

**Atomic write:** Pipe the staged content through `python3 {atomicWriteHelper} write --target {outputFile}`: a plain `rm`+rewrite risks a partial write corrupting the report.

On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:report`, with `"path": "{outputFile}"` and no `report_path`: the report was not written.

### 5. Display Initialization Summary

"**Stack Verification Initialized**

| Field | Value |
|-------|-------|
| **Skills Loaded** | {skill_count} |
| **Architecture Doc** | {architecture_doc} |
| **PRD Document** | {prd_doc or 'Not provided — requirements pass will be skipped'} |
| **Previous Report** | {previousReport or 'Not provided — no delta comparison'} |

**Skill Inventory:**

| Skill | Exports | Exports source | Confidence |
|-------|---------|----------------|------------|
| {name} | {number of exports} | {exports_source} | {confidence} |

**Proceeding to coverage analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


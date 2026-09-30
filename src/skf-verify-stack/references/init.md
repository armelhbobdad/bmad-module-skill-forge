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

**Bind `{project_slug}`.** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins. Run:

```bash
uv run {validateFeasibilityReportHelper} --locate "{outputFolderPath}" --project-name "{project_name}"
```

Bind `{project_slug}` ← `projectSlug`, whatever `status` says: this run needs only the slug, and the helper holds the one slug rule that the consumers of this report apply when they look for it. If no candidate exists, or the command prints no JSON: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

### 1. Accept Input Documents

"**Verify Stack — Feasibility Analysis** (read-only — never modifies your skills, architecture doc, or PRD).

If you meant to *generate* skills first, type `cancel` and run `[CS] Create Skill` or `[QS] Quick Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc
2. **PRD or vision document path** (OPTIONAL) — for requirements coverage analysis
3. **Previous feasibility report path** (OPTIONAL): a timestamped report from an earlier run, for delta comparison. Leave it empty to compare against the most recent one found.

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

Wait for user input. **GATE [default: use args]** — If `{headless_mode}` and `--architecture-doc` was provided: use that path and auto-proceed, log: "headless: using provided architecture path". If `--prd` and/or `--previous-report` were provided, consume them at the corresponding sub-validations below. If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) and emit the error envelope.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt below: Display "Cancelled — no analysis was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable → "Architecture document not found at `{path}`. Provide a valid path."
- HALT (exit code 2, `halt_reason: "input-invalid"`) if the user cannot provide a valid path. In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" immediately.

**Validate PRD document (if provided):**
- Confirm the file exists and is readable
- If missing → "PRD document not found at `{path}`. Proceeding without PRD — requirements pass will be skipped."
- Store PRD availability as `prdAvailable: true|false`

**Resolve the previous report.** Run the previous-report helper, with `--provided` set to the path when `--previous-report` or the prompt gave one, and without it otherwise:

```bash
uv run {previousReportScript} --folder "{outputFolderPath}" --slug "{project_slug}" --timestamp "{timestamp}" [--provided "<path>"]
```

It never returns a file this run writes: §4 overwrites `{outputFile}` and `{outputFileLatest}` before synthesize reads the previous report, so comparing against either would compare the run with itself. It compares files, not path strings, so a link or another spelling of either file still counts. Without a path it picks the newest timestamped report of this project in `{outputFolderPath}`: every run writes one, so a prior report usually persists with no manual backup. When it prints no JSON (exit 2, a usage error), the line it prints names the flag it rejected: fix that flag's value and run it again. Otherwise branch on `status`:

- `collision` (exit 1): "`{provided}` is `{collidesWith}`, which this run overwrites. Give a timestamped report from an earlier run, or leave the path empty to compare against the most recent one." Interactive: wait for the answer, run the helper again with `--provided` set to it (or without `--provided` for an empty answer), and branch on its `status` as here. In headless, where the path came from `--previous-report`: HALT (exit code 5, `halt_reason: "previous-report-collision"`) and emit the error envelope.
- `not-found`: "Previous report not found at `{provided}`. Proceeding without delta comparison." Set `previousReport` to empty.
- `provided`: set `previousReport` to the returned `previousReport`.
- `discovered` (no path was given): interactive, offer "Found a prior report from `{previousTimestamp}`: compare against it? **[Y]** use it / paste a different path / **[skip]** / **[X]** cancel". On [Y], set `previousReport` to the returned `previousReport`; on a pasted path, run the helper again with `--provided` set to it and branch on its `status` as above; on `skip`, leave `previousReport` empty; on [X], cancel as above (exit code 6).
  **GATE [default: Y]**: if `{headless_mode}`, set `previousReport` to the returned `previousReport` and log: "headless: delta comparison against `{previousReport}`".
- `none`: leave `previousReport` empty (first run, no delta).

### 2. Scan Skills Folder

**Pre-flight — skills folder existence:**
- If `{skills_output_folder}` does not exist on disk: HALT (exit code 3, `halt_reason: "skills-folder-missing"`) with "**Cannot proceed.** `{skills_output_folder}` does not exist — run **[SF] Setup Forge** to initialize the forge, then generate skills with [CS] or [QS]." In headless, emit the error envelope.
- If `{skills_output_folder}` exists but is empty (no subdirectories at all): HALT (exit code 3, `halt_reason: "skills-folder-missing"`) with "**Cannot proceed.** `{skills_output_folder}` contains 0 skills. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]." In headless, emit the error envelope.

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

**Enumerate the skills with the shared helper:**

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability
```

The helper reads only the skills SKF generated. For each top-level folder (links, dot-names, `_batch` and `.skf-` names aside) it takes the version the `active` link names when that version's `{name}/metadata.json` carries an SKF marker, else the highest version whose `metadata.json` does, else a flat root `SKILL.md` beside a marked `metadata.json`; it never reads the export manifest. It resolves that package's exports from `metadata.json` `exports`, else a `references/*.md` `## API` or `## Exports` section, else a SKILL.md `## Exports` or `## API Surface` section, and follows `composes:` to find cycles. Each `skills[]` entry has `name` (the folder name), `path` (the package, relative to `{skills_output_folder}`: `x/active/x`, `x/<version>/x` or `x`), `exports`, `exports_source` (`metadata`, `references`, `skill-md` or `unknown`), `confidence` (`T1`, `T2` or `T1-low`, from the exports source, not metadata's `confidence_tier`), `metadata_hash`, `evidence_tier` (`T1`, `T1-low`, `T2` or `T3`: the largest bin of the package's `confidence_distribution`, one scale for every skill type, which synthesize's delta compares and the report records), `confidence_tier` (metadata.json's value when it belongs to the scale of its `skill_type`, else null), `metadata_schema_version` (metadata.json `spec_version`, or null), and `language` (a string, or a list for a stack) and `exports_documented` (metadata.json `stats.exports_documented`), which the integrations stage reads instead of opening `metadata.json`. `warnings[]` names per-skill problems, each starting `<name>: `: a `metadata.json` or version folder that cannot be read (including one that keeps SKF from telling whether it generated the folder), an SKF package with no `SKILL.md`, no exports found, and `composes` cycles; a folder with no skill in it is skipped silently. Cache the result as `skill_inventory` (used by §3, §4, §5, the coverage and integrations stages, and synthesize's delta and Evidence Sources table), and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count` and `{inventory_warnings}` ← `warnings`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders, such as a module's own skills in a shared skills folder, are not in `skills[]` and count toward neither `{skill_count}` nor `{warning_count}`.

`--reliability` adds `inventory_reliable` (bool), `unreliable_ratio` (float), `skill_count` and `warning_count`, over the skills SKF generated and their warnings.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with: "Inventory scan unreliable — {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [VS]." In headless, emit the error envelope. The helper's threshold is chosen so a single malformed skill in a small 3-5 skill inventory does not trip the halt.

**Capture mtime:** For each skill in `skill_inventory`, record the modification time of `{skills_output_folder}/{path}/metadata.json` into the entry as `metadata_mtime`. Step-03 will re-verify this to detect mid-run modifications.

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 2 skills SKF generated must exist (`{skill_count}`; a stack requires multiple libraries)
- If fewer than 2 → "**Cannot proceed.** Only {skill_count} skill(s) SKF generated were found in `{skills_output_folder}`. A stack requires at least 2 skills. Generate more skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]." When `{not_skf_output}` is non-empty, append: "Skipped (not SKF output): {not_skf_output}."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`). In headless, emit the error envelope.

**Check forge_data_folder:**
- Verify `forge_data_folder` was resolved from config.yaml and is non-empty
- If undefined or empty → "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Re-run [SF] Setup Forge to initialize."
- HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`). In headless, emit the error envelope.

### 4. Create Feasibility Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

This skill produces the feasibility report schema defined in `{feasibilitySchemaRef}`; every output conforms to that schema — `schemaVersion: "1.0"`, the verdict token set (`Verified|Plausible|Risky|Blocked`; overall `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE`), the filename pattern, and the section-heading order.

**Filename variables:** `timestamp` was fixed at activation (SKILL.md On Activation §2) and `project_slug` by the Bind block at the top of this step; reuse them, do not re-derive. `{outputFile}` and `{outputFileLatest}` resolve from them per the stage frontmatter template, the latter as a copy, not a symlink (per schema).

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

**Atomic write:** Pipe the staged content through `python3 {atomicWriteHelper} write --target {outputFile}` and then again with `--target {outputFileLatest}`. Both writes use the same staged content through the atomic helper — a plain `rm`+rewrite risks a partial write corrupting the report, and the `-latest` file is a copy, not a symlink (per the shared schema).

On any non-zero exit from either write: HALT (exit code 4, `halt_reason: "write-failed"`) and emit the error envelope per SKILL.md "Result Contract (Headless)" with `report_path: null`, `report_latest_path: null`, `overall_verdict: null`.

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


---
nextStepFile: './step-02-coverage.md'
reportTemplate: 'assets/feasibility-report-template.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 1: Initialize Verification

## STEP GOAL:

Load all generated skills from the skills output folder, accept the architecture document path (required) and optional PRD/vision document path from the user, validate that all inputs exist and are readable, create the feasibility report document, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and creating the report skeleton — do not perform analysis
- Auto-proceed — halts only on validation errors

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Accept Input Documents

"**Verify Stack — Feasibility Analysis**

Please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc
2. **PRD or vision document path** (OPTIONAL) — for requirements coverage analysis
3. **Previous feasibility report path** (OPTIONAL) — for delta comparison with a prior run (provide a backup copy)"

Wait for user input. **GATE [default: use args]** — If `{headless_mode}` and architecture doc path was provided as argument: use that path and auto-proceed, log: "headless: using provided architecture path".

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable → "Architecture document not found at `{path}`. Provide a valid path."
- HALT until a valid architecture document is provided

**Validate PRD document (if provided):**
- Confirm the file exists and is readable
- If missing → "PRD document not found at `{path}`. Proceeding without PRD — requirements pass will be skipped."
- Store PRD availability as `prd_available: true|false`

**Validate previous report (if provided):**
- Confirm the file exists and is readable
- **Collision check:** Resolve both the provided path and `{outputFile}` to their absolute form before comparing (do not rely on string equality alone). If they resolve to the same location, warn: "The previous report path points to the same location as the new report. This file will be overwritten during this run. Provide a path to a backup copy, or leave empty to skip delta comparison." HALT until resolved.
- If missing → "Previous report not found at `{path}`. Proceeding without delta comparison."
- Store as `previous_report: {path}` (or empty string if not provided)

### 2. Scan Skills Folder

Read the `{skills_output_folder}` directory. Skills use a version-nested directory structure (see `knowledge/version-paths.md`).

**Version-aware skill discovery:**
1. Read `{skills_output_folder}/.export-manifest.json` if it exists. For each skill in `exports`, use `active_version` to resolve `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. For any subdirectory not covered by the manifest, check for an `active` symlink at `{skills_output_folder}/{dir_name}/active` — resolve to `{skill_group}/active/{dir_name}/`
3. Fall back to flat path `{skills_output_folder}/{dir_name}/` for unmigrated skills

For each resolved skill package, check for the presence of `SKILL.md` and `metadata.json`.

<!-- Subagent delegation: read metadata.json files in parallel, return compact JSON -->

**Read all metadata.json files in parallel using subagents.** Launch up to **8 subagents concurrently** (batch larger inventories in rounds of 8). Each subagent receives one resolved skill package path and MUST:
1. Read `{skill_package}/metadata.json`
2. ONLY return this compact JSON — no prose, no extra commentary:

```json
{
  "skill_name": "...",
  "language": "...",
  "confidence_tier": "...",
  "exports_documented": 0,
  "source_repo": "...",
  "source_root": "..."
}
```

Parent collects all subagent JSON summaries. Fields map directly from metadata.json:
- `skill_name` ← `name`
- `language` ← `language`
- `confidence_tier` ← `confidence_tier`
- `exports_documented` ← `stats.exports_documented`
- `source_repo` ← `source_repo` (or empty string if absent)
- `source_root` ← `source_root` (or empty string if absent)

**Build a skill inventory** as an internal list of all loaded skills with the fields above.

**If a resolved skill package lacks SKILL.md or metadata.json:**
- Log: "Skipping `{dir_name}` — missing SKILL.md or metadata.json"
- Do not include in inventory

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 2 valid skills must exist (a stack requires multiple libraries)
- If fewer than 2 → "**Cannot proceed.** Only {count} skill(s) found in `{skills_output_folder}`. A stack requires at least 2 skills. Generate more skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]."
- HALT workflow

**Check forge_data_folder:**
- Verify `forge_data_folder` was resolved from config.yaml and is non-empty
- If undefined or empty → "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Re-run [SF] Setup Forge to initialize."
- HALT workflow

**Check architecture document:**
- Confirm it was loaded successfully in section 1
- If not → HALT with error (should not reach here if section 1 validation passed)

### 4. Create Feasibility Report

Load `{reportTemplate}` and create the output file at `{outputFile}`.

**Populate frontmatter:**
- `project_name`, `date`, `architecture_doc`, `prd_doc` (or "none")
- `prd_available: true|false` (from section 1 validation)
- `previous_report: {path}` (or empty string if not provided)
- `skills_analyzed: {count}`
- `overall_verdict: "pending"`
- `stepsCompleted: ['step-01-init']`

### 5. Display Initialization Summary

"**Stack Verification Initialized**

| Field | Value |
|-------|-------|
| **Skills Loaded** | {count} |
| **Architecture Doc** | {architecture_doc} |
| **PRD Document** | {prd_doc or 'Not provided — requirements pass will be skipped'} |
| **Previous Report** | {previous_report or 'Not provided — no delta comparison'} |

**Skill Inventory:**

| Skill | Language | Tier | Exports |
|-------|----------|------|---------|
| {skill_name} | {language} | {confidence_tier} | {exports_documented} |

**Proceeding to coverage analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


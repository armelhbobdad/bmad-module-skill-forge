---
nextStepFile: './step-02-gap-analysis.md'
refinementRulesData: 'references/refinement-rules.md'
---

# Step 1: Initialize Refinement

## STEP GOAL:

Load the architecture document (required), scan the skills folder to build a skill inventory with metadata, load the optional VS feasibility report for context, validate that all inputs exist and meet minimum requirements, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and validating prerequisites — do not perform analysis
- Present a clear initialization summary so downstream steps have validated inputs

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Accept Input Documents

"**Refine Architecture — Evidence-Backed Refinement**

Please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc to refine
2. **VS feasibility report path** (OPTIONAL) — from a previous [VS] Verify Stack run, for additional context"

Wait for user input. Store the validated architecture document path as `architecture_doc`. **GATE [default: use args]** — If `{headless_mode}` and architecture doc path was provided as argument: use that path and auto-proceed, log: "headless: using provided architecture path".

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable: "Architecture document not found at `{path}`. Provide a valid path."
- HALT until a valid architecture document is provided

**Validate VS report (if provided):**
- Confirm the file exists and is readable
- If missing at user-provided path: attempt auto-probe (below) before giving up
- Store VS report availability as `vs_report_available: true|false` and `vs_report_path`

### 2. Scan Skills Folder

Read the `{skills_output_folder}` directory. Skills use a version-nested directory structure (see `knowledge/version-paths.md`).

**Version-aware skill discovery:**
1. Read `{skills_output_folder}/.export-manifest.json` if it exists. For each skill in `exports`, use `active_version` to resolve `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. For any subdirectory not covered by the manifest, check for an `active` symlink at `{skills_output_folder}/{dir_name}/active` — resolve to `{skill_group}/active/{dir_name}/`
3. Fall back to flat path `{skills_output_folder}/{dir_name}/` for unmigrated skills

For each resolved skill package, check for the presence of `SKILL.md` and `metadata.json`.

**For each valid skill directory, extract from metadata.json:**
- `name` — skill name
- `language` — primary language
- `confidence_tier` — Quick, Forge, Forge+, or Deep
- `exports_documented` — read from `stats.exports_documented` in metadata.json (count of documented exports)
- `source_repo` or `source_root` — original source repository

**Build a skill inventory** as an internal list of all loaded skills with the fields above.

**If a resolved skill package lacks SKILL.md or metadata.json:**
- Log: "Skipping `{dir_name}` — missing SKILL.md or metadata.json"
- Do not include in inventory

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 1 valid skill must exist
- If no skills found: "**Cannot proceed.** No skills found in `{skills_output_folder}`. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [RA]."
- HALT workflow
- If exactly 1 valid skill found: "⚠️ Proceeding with 1 skill. Note: gap analysis will find no gaps — pairwise analysis requires at least 2 skills. Step 02 will still execute and issue an appropriate notice. Issue detection and improvement detection will proceed normally."

**Check output_folder:**
- Verify `output_folder` was resolved from config.yaml and is non-empty
- If undefined or empty: "**Cannot proceed.** `output_folder` is not configured in config.yaml. Add an `output_folder` path and re-run [RA]."
- HALT workflow
- Verify the `output_folder` directory exists. If it does not exist, create it. HALT with error if creation fails.

**Check forge_data_folder:**
- Verify `forge_data_folder` was resolved from config.yaml and is non-empty
- If undefined or empty: "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Add a `forge_data_folder` path to your config.yaml and re-run [RA]."
- HALT workflow
- Verify the `forge_data_folder` directory exists. If it does not exist, attempt to create it. If creation fails: "**Cannot proceed.** `forge_data_folder` at `{forge_data_folder}` does not exist and could not be created. Create the directory manually and re-run [RA]."
- HALT workflow on creation failure

**Check architecture document:**
- Confirm it was loaded successfully in section 1
- If not: HALT with error (should not reach here if section 1 validation passed)

### 3b. Auto-Probe VS Report

**Auto-probe VS report (if not provided by user in section 1, OR if user-provided path was invalid):**
- Only attempt if `forge_data_folder` is non-empty and the directory exists (validated above); otherwise skip probe and set `vs_report_available: false`
- Check for `{forge_data_folder}/feasibility-report-{project_name}.md`
- If found: "Auto-discovered VS report at `{path}`. Loading for additional context."
- Store `vs_report_available: true` and `vs_report_path`
- If not found: `vs_report_available: false` — "Proceeding without VS report — issue detection will rely on skill data only."

### 3c. Reset RA State File

Create (or overwrite) `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header:

```markdown
<!-- RA state for {project_name} — generated {current_date} -->
```

This ensures steps 02-04 append to a clean slate and context recovery in step-05 never loads stale findings from a prior run.

### 4. Load Refinement Rules

Load `{refinementRulesData}` for reference by downstream steps.

Extract: gap detection rules, issue detection rules, improvement detection rules, citation format, and preservation rules.

### 5. Display Initialization Summary

"**Architecture Refinement Initialized**

| Field | Value |
|-------|-------|
| **Architecture Doc** | {architecture_doc} |
| **VS Report** | {vs_report_path or 'Not provided — issue detection will use skill data only'} |
| **Skills Loaded** | {skill_count} |

**Skill Inventory:**

| Skill | Language | Tier | Exports |
|-------|----------|------|---------|
| {skill_name} | {language} | {confidence_tier} | {exports_documented} |

**Proceeding to gap analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


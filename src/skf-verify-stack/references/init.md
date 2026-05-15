---
nextStepFile: 'coverage.md'
reportTemplate: 'assets/feasibility-report-template.md'
feasibilitySchemaRef: 'src/shared/references/feasibility-report-schema.md'
atomicWriteScript: '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{forge_data_folder}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{forge_data_folder}/feasibility-report-{project_slug}-latest.md'
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
- Store PRD availability as `prdAvailable: true|false`

**Validate previous report (if provided):**
- Confirm the file exists and is readable
- **Collision check:** Compare both the provided path and `{outputFile}` via `(st_dev, st_ino)` tuples obtained from `stat(2)` on each path (do not rely on absolute-path string equality — symlinks, bind mounts, and case-insensitive filesystems can defeat string comparison; the `(st_dev, st_ino)` comparison is the canonical kernel-level equivalent of `os.path.realpath`-based equality and is strictly stronger because it also catches hardlinks). If `{outputFile}` does not yet exist, resolve its parent via `realpath`, stat that directory, and combine `(st_dev, parent_ino, basename)` for comparison. If the two paths resolve to the same inode, warn: "The previous report path points to the same inode as the new report. This file will be overwritten during this run. Provide a path to a backup copy, or leave empty to skip delta comparison." HALT until resolved.
- If missing → "Previous report not found at `{path}`. Proceeding without delta comparison."
- Store as `previousReport: {path}` (or empty string if not provided)

### 2. Scan Skills Folder

**Pre-flight — skills folder existence:**
- If `{skills_output_folder}` does not exist on disk: HALT with "**Cannot proceed.** `{skills_output_folder}` does not exist — run **[SF] Setup Forge** to initialize the forge, then generate skills with [CS] or [QS]."
- If `{skills_output_folder}` exists but is empty (no subdirectories at all): HALT with "**Cannot proceed.** `{skills_output_folder}` contains 0 skills. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]."

Read the `{skills_output_folder}` directory. Skills use a version-nested directory structure (see `knowledge/version-paths.md`).

**Version-aware skill discovery:**
1. Read `{skills_output_folder}/.export-manifest.json` if it exists. For each skill in `exports`, use `active_version` to resolve `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. For any subdirectory not covered by the manifest, check for an `active` symlink at `{skills_output_folder}/{dir_name}/active` — resolve to `{skill_group}/active/{dir_name}/`
3. Fall back to flat path `{skills_output_folder}/{dir_name}/` for unmigrated skills

For each resolved skill package, check for the presence of `SKILL.md`, `metadata.json`, and `bmad-skill-manifest.yaml`. If `bmad-skill-manifest.yaml` is missing in the resolved package, log "Skipping `{dir_name}` — missing bmad-skill-manifest.yaml" and exclude from inventory (do not spawn a subagent).

**Non-symlink `active` check:** When resolving via the `active` symlink pattern (case 2 above), perform an explicit `is_symlink` check on `{skills_output_folder}/{dir_name}/active`. If the path exists but is NOT a symlink, log "Skipping `{dir_name}` — `active` is not a symlink (repair with [SKF-update-skill])" and treat as missing.

**Orphan-versions detection:** For any `{skills_output_folder}/{dir_name}/` that contains subdirectories matching semver (`^\d+\.\d+\.\d+`) but has no `active` symlink at all, emit: "**Error:** Skill `{dir_name}` has versions `{list_of_version_dirs}` but no `active` symlink — run [SKF-update-skill] to repair before re-running [VS]." Exclude the skill from inventory; count it toward the failure budget for the run summary.

<!-- Subagent delegation: read metadata.json files in parallel, return compact JSON -->

**Read all metadata.json files in parallel using subagents.** Launch up to **8 subagents concurrently** (batch larger inventories in rounds of 8 — the 8-way cap keeps the aggregate token window for the parent manageable while still parallelizing most typical stack sizes; tune in a future minor if inventories routinely exceed ~40 skills). Each subagent receives one resolved skill package path and MUST:
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

**Subagent JSON schema validation:** For each subagent response, require keys `skill_name`, `language`, and an integer `exports_documented`. Wrap each JSON parse in try/catch. On parse failure or missing required key, log "Skipping `{dir_name}` — metadata.json unparseable (skill may be under active modification)" and exclude from the inventory. If more than **20%** (the failure-budget threshold — chosen so a single malformed skill in a small 3-5 skill inventory does not trip the halt, while larger inventories still halt before evidence quality collapses) of subagent calls fail schema validation, HALT the workflow with: "Inventory scan unreliable — {failed_count}/{total_count} skills returned malformed metadata. Re-run [VS] after skills stabilize."

**Capture mtime:** For each accepted skill, also record `metadata.json`'s mtime (via `stat`) into the inventory as `metadata_mtime`. Step-03 will re-verify this to detect mid-run modifications.

**metadata_schema_version check:** For each accepted skill, read `metadata_schema_version` from `metadata.json`. If missing or below minimum (`1.0`), log "Skipping `{dir_name}` — metadata_schema_version `{value}` below minimum `1.0`. Re-run [SKF-update-skill] to migrate." and exclude from the inventory.

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

This skill is the PRODUCER of the feasibility report schema defined in `{feasibilitySchemaRef}`. All outputs MUST conform to that schema — in particular: `schemaVersion: "1.0"`, the defined verdict token set (`Verified|Plausible|Risky|Blocked`; overall `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE`), the filename pattern, and the section-heading order.

**Compute filename variables:**
- `project_slug`: slugify `project_name` (lowercase, hyphens only, no unicode, no whitespace)
- `timestamp`: UTC `YYYYMMDD-HHmmss` captured at step 1 start
- `outputFile` resolves to `{forge_data_folder}/feasibility-report-{project_slug}-{timestamp}.md`
- `outputFileLatest` resolves to `{forge_data_folder}/feasibility-report-{project_slug}-latest.md` (a copy, not a symlink — per schema)

**Load** `{reportTemplate}` and stage the initial content.

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
- `skillsAnalyzed: {count}`
- `stepsCompleted: ['init']`

**Atomic write:** Pipe the staged content through `python3 {atomicWriteScript} write --target {outputFile}` and then again with `--target {outputFileLatest}`. Both writes use the same staged content. Do NOT use `rm`+rewrite; do NOT create a symlink for the `-latest` copy.

### 5. Display Initialization Summary

"**Stack Verification Initialized**

| Field | Value |
|-------|-------|
| **Skills Loaded** | {count} |
| **Architecture Doc** | {architecture_doc} |
| **PRD Document** | {prd_doc or 'Not provided — requirements pass will be skipped'} |
| **Previous Report** | {previousReport or 'Not provided — no delta comparison'} |

**Skill Inventory:**

| Skill | Language | Tier | Exports |
|-------|----------|------|---------|
| {skill_name} | {language} | {confidence_tier} | {exports_documented} |

**Proceeding to coverage analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


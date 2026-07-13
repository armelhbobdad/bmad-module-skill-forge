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
# it for the deterministic skills inventory (cascade-resolved exports,
# metadata-hash for change-detection, confidence-tier mapping). If neither
# candidate exists, §2 does NOT halt — it falls through to the LLM-driven
# subagent fan-out as graceful degradation (see §2).
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
---

<!-- Config: communicate in {communication_language}. Initialize the feasibility report skeleton in {document_output_language}. -->

# Step 1: Initialize Verification

## STEP GOAL:

Load all generated skills from the skills output folder, accept the architecture document path (required) and optional PRD/vision document path from the user, validate that all inputs exist and are readable, create the feasibility report document, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and creating the report skeleton — do not perform analysis
- Auto-proceed — halts only on validation errors

## MANDATORY SEQUENCE

### 1. Accept Input Documents

"**Verify Stack — Feasibility Analysis** (read-only — never modifies your skills, architecture doc, or PRD).

If you meant to *generate* skills first, type `cancel` and run `[CS] Create Skill` or `[QS] Quick Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc
2. **PRD or vision document path** (OPTIONAL) — for requirements coverage analysis
3. **Previous feasibility report path** (OPTIONAL) — for delta comparison with a prior run (provide a backup copy)

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

**Validate previous report (if provided):**
- Confirm the file exists and is readable
- **Collision check:** Resolve `{outputFile}` from the activation-stored `{outputFolderPath}`, `{project_slug}`, and `{timestamp}`. Then compare both the provided path and `{outputFile}` via `(st_dev, st_ino)` tuples obtained from `stat(2)` on each path (do not rely on absolute-path string equality — symlinks, bind mounts, and case-insensitive filesystems can defeat string comparison). If `{outputFile}` does not yet exist, resolve its parent via `realpath`, stat that directory, and combine `(st_dev, parent_ino, basename)` for comparison. If the two paths resolve to the same inode, warn: "The previous report path points to the same inode as the new report. This file will be overwritten during this run. Provide a path to a backup copy, or leave empty to skip delta comparison." HALT (exit code 5, `halt_reason: "previous-report-collision"`) until resolved. In headless, emit the error envelope.
- If missing → "Previous report not found at `{path}`. Proceeding without delta comparison."
- Store as `previousReport: {path}` (or empty string if not provided)

**Auto-discover a prior report (only when none was provided above):** If neither `--previous-report` nor an interactive previous-report path was given, glob `{outputFolderPath}` for `feasibility-report-{project_slug}-*.md`, excluding this run's `{timestamp}` file and `feasibility-report-{project_slug}-latest.md`. Every run writes a new timestamped report, so a usable prior usually already persists on disk with no manual backup. If one or more matches remain, pick the most recent by the embedded `YYYYMMDD-HHmmss` timestamp:
- Interactive: offer "Found a prior report from `{date}` — compare against it? **[Y]** use it / paste a different path / **[skip]**". On [Y], set `previousReport` to that path; on a pasted path, use it; on `skip`, leave `previousReport` empty.
- **GATE [default: Y]** — If `{headless_mode}`: auto-select the most recent match, set `previousReport` to it, log: "headless: delta comparison against `{path}`".
- Excluding this run's `{timestamp}` and `-latest` files guarantees the auto-selected path is a distinct inode from `{outputFile}`, so it can never trip the collision check above.
- If no match remains, leave `previousReport` empty — first run, no delta.

### 2. Scan Skills Folder

**Pre-flight — skills folder existence:**
- If `{skills_output_folder}` does not exist on disk: HALT (exit code 3, `halt_reason: "skills-folder-missing"`) with "**Cannot proceed.** `{skills_output_folder}` does not exist — run **[SF] Setup Forge** to initialize the forge, then generate skills with [CS] or [QS]." In headless, emit the error envelope.
- If `{skills_output_folder}` exists but is empty (no subdirectories at all): HALT (exit code 3, `halt_reason: "skills-folder-missing"`) with "**Cannot proceed.** `{skills_output_folder}` contains 0 skills. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]." In headless, emit the error envelope.

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins.

**Primary path — deterministic enumeration via shared helper:**

```bash
python3 {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability
```

The helper walks `{skills_output_folder}`, reads each `metadata.json`, applies the exports cascade (metadata → references/ → SKILL.md prose), maps `confidence_tier` (T1/T2/T1-low), captures stack-skill cycles via `composes:`, and emits structured JSON with one entry per skill plus a top-level `warnings[]` array. Cache the result as `skill_inventory` (used by §3, §4, §5, and the integrations + coverage stages).

Each helper-emitted entry includes: `skill_name`, `version`, `language`, `confidence_tier`, `exports` (cascade-resolved), `source_repo`, `source_root`, plus a `metadata_hash` for change-detection across runs. The helper's `warnings[]` carries per-skill skip reasons (missing manifest, malformed JSON, non-symlink `active`, orphan-versions, schema-version violations).

`--reliability` additionally attaches the inventory reliability verdict: `inventory_reliable` (bool), `unreliable_ratio` (float), `skill_count`, and `warning_count`.

**Failure-budget guard:** Read `inventory_reliable` from the helper JSON. If it is `false`, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with: "Inventory scan unreliable — {warning_count}/{skill_count + warning_count} skills returned malformed metadata or skip warnings. Re-run [VS] after skills stabilize." (substitute `warning_count` and `skill_count + warning_count` from the helper JSON). In headless, emit the error envelope. The helper's threshold is chosen so a single malformed skill in a small 3-5 skill inventory does not trip the halt.

**Capture mtime:** For each accepted skill in `skill_inventory`, also record `metadata.json`'s mtime via `stat` into the entry as `metadata_mtime`. Step-03 will re-verify this to detect mid-run modifications.

**Fallback path — graceful degradation when the helper is unavailable:** If `{enumerateStackSkillsHelper}` has no existing candidate (e.g. partial installation), fall through to the LLM-driven subagent fan-out: launch up to **8 subagents concurrently**, each reading one resolved skill package's `metadata.json` and returning the same JSON shape the helper would emit. In this branch `inventory_reliable` is unavailable, so compute the failure-budget guard inline: when `warning_count / (skill_count + warning_count) > 0.20`, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with the same message as the primary path. In headless, emit the error envelope.

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 2 valid skills must exist (a stack requires multiple libraries)
- If fewer than 2 → "**Cannot proceed.** Only {count} skill(s) found in `{skills_output_folder}`. A stack requires at least 2 skills. Generate more skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`). In headless, emit the error envelope.

**Check forge_data_folder:**
- Verify `forge_data_folder` was resolved from config.yaml and is non-empty
- If undefined or empty → "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Re-run [SF] Setup Forge to initialize."
- HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`). In headless, emit the error envelope.

### 4. Create Feasibility Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

This skill produces the feasibility report schema defined in `{feasibilitySchemaRef}`; every output conforms to that schema — `schemaVersion: "1.0"`, the verdict token set (`Verified|Plausible|Risky|Blocked`; overall `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE`), the filename pattern, and the section-heading order.

**Filename variables:** `project_slug` and `timestamp` were fixed at activation per SKILL.md On Activation §2; reuse them, do not re-derive. `{outputFile}` and `{outputFileLatest}` resolve from them per the stage frontmatter template — the latter a copy, not a symlink (per schema).

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
- `skillsAnalyzed: {count}`
- `stepsCompleted: ['init']`

**Atomic write:** Pipe the staged content through `python3 {atomicWriteHelper} write --target {outputFile}` and then again with `--target {outputFileLatest}`. Both writes use the same staged content through the atomic helper — a plain `rm`+rewrite risks a partial write corrupting the report, and the `-latest` file is a copy, not a symlink (per the shared schema).

On any non-zero exit from either write: HALT (exit code 4, `halt_reason: "write-failed"`) and emit the error envelope per SKILL.md "Result Contract (Headless)" with `report_path: null`, `report_latest_path: null`, `overall_verdict: null`.

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


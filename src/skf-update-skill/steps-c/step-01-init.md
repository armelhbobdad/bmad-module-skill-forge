---
nextStepFile: './step-02-detect-changes.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
---

# Step 1: Initialize Update

## STEP GOAL:

Load the existing skill and all its provenance data, detect whether this is an individual or stack skill, load the forge tier configuration, and present a baseline summary so the user can confirm the update scope before proceeding.

## Rules

- Focus only on loading existing artifacts and establishing the baseline — read-only operations
- Do not begin change detection (Step 02)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Request Skill Path

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves via version-aware path resolution — see `knowledge/version-paths.md`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection

**Skill:** {user provides path or name}"

**Version-Aware Path Resolution:**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill-name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading

Resolve the path to an absolute skill folder location.

**If `--from-test-report` was provided (or user references a test report):**
Search for the test report at `{forge_data_folder}/{skill_name}/{active_version}/test-report-{skill_name}.md` (i.e., `{forge_version}/test-report-{skill_name}.md`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/test-report-{skill_name}.md`. If found, set `test_report_path` in context and `update_mode: gap-driven`. If not found at either path, warn and continue with normal source drift mode.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_package}/SKILL.md`
- If missing: **ABORT** — "No SKILL.md found at `{resolved_skill_package}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_package}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_root`
- If missing: **ABORT** — "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

**Detect skill type from metadata:**
- If `skill_type == "single"` or absent: flag as single skill
- If `skill_type == "stack"`: flag as stack skill (multi-file update mode)

### Stack Skill Guard

After loading metadata.json, check `skill_type`:
- If `skill_type` is `"stack"`: display message:
  "**Stack skills cannot be surgically updated.** Stack skills compose exports from multiple sources — surgical re-extraction requires re-running the full composition pipeline.
  
  **To update this stack skill**, run `skf-create-stack-skill` with the same project path. It will re-analyze manifests (code-mode) or re-read constituent skills (compose-mode) and produce an updated stack.
  
  If you came here from an audit report, the drift report identifies which constituent libraries changed — use that to decide whether re-composition is needed."
- Exit the workflow (do not proceed to step-02)

### 3. Load Forge Tier Configuration

**Load `{sidecar_path}/forge-tier.yaml`:**
- Extract: `tier` (Quick, Forge, Forge+, or Deep), available tools
- If missing: **ABORT** — "No forge-tier.yaml found. Run setup first to detect available tools."

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**Determine analysis capabilities:**
- **Quick:** text pattern matching only → T1-low confidence
- **Forge:** AST structural extraction → T1 confidence
- **Forge+:** AST structural extraction + CCC semantic ranking → T1 confidence (with ccc signals)
- **Deep:** AST + QMD semantic enrichment → T1 + T2 confidence

### 4. Load Provenance Map

**Load `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json`** (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`:
- Extract: export list, file mappings, extraction timestamps, confidence tiers
- Calculate provenance age (days since last extraction)

**If provenance map missing at both paths:**

"**WARNING:** No provenance map found at `{forge_version}/provenance-map.json` or flat fallback.

Without a provenance map, update-skill cannot perform targeted change detection. Options:

**[D]egraded mode** — Perform full re-extraction with T1-low confidence (equivalent to re-running create-skill but preserving [MANUAL] sections)
**[X]** — Abort and run create-skill first to generate provenance data

Select: [D] Degraded / [X] Abort"

- If D: set `degraded_mode = true`, proceed with full extraction scope
- If X: **ABORT**

### 5. Load [MANUAL] Section Inventory

Load {manualSectionRulesFile} to understand [MANUAL] detection patterns.

**Scan SKILL.md for [MANUAL] sections:**
- Count all `<!-- [MANUAL:*] -->` markers
- Map each [MANUAL] block to its parent section (by heading hierarchy)
- Record section names and approximate line positions

**For stack skills, also scan:**
- All `references/*.md` files for [MANUAL] markers
- All `references/integrations/*.md` files for [MANUAL] markers

### 6. Resolve Source Code Path

**From provenance map (if available):**
- Extract `source_root` path
- Validate source path exists and is accessible

**If source path invalid or missing:**

"**Source path from provenance map is invalid:** `{source_root}`

Please provide the current source code path:
**Path:** {user provides path}"

### 7. Present Baseline Summary

"**Update Skill Baseline:**

| Property | Value |
|----------|-------|
| **Skill** | {skill_name} |
| **Type** | {single/stack} |
| **Version** | {version} |
| **Created** | {created date} |
| **Source** | {source_root} |
| **Forge Tier** | {forge_tier} (current) vs {original_tier} (at creation) |
| **Provenance Age** | {days} days since last extraction |
| **Exports** | {export_count} tracked exports |
| **[MANUAL] Sections** | {manual_count} preserved sections |
| **Mode** | {normal/degraded/gap-driven} |

**Analysis plan:** {tier_description}
- {Quick: text pattern diff → T1-low findings}
- {Forge: AST structural diff → T1 findings}
- {Deep: AST structural + QMD semantic diff → T1 + T2 findings}

**Ready to detect changes and update this skill?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Change Detection"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past update confirmation"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C] is selected and baseline has been established with all required artifacts loaded, will you then load and read fully `{nextStepFile}` to execute change detection.


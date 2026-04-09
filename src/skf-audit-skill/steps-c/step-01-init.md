---
nextStepFile: './step-02-re-index.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
templateFile: 'assets/drift-report-template.md'
---

# Step 1: Initialize Audit

## STEP GOAL:

Load the existing skill artifacts, provenance map, and forge tier configuration to establish the baseline for drift detection. Create the drift report document and present a baseline summary for user confirmation before proceeding with analysis.

## Rules

- Focus only on loading skill artifacts and establishing the baseline — do not perform any diff or analysis
- Do not proceed if skill path is invalid or SKILL.md not found
- Present baseline summary clearly so user can confirm before analysis begins
- Docs-only limitation: If `metadata.json` indicates `source_type: "docs-only"` or `confidence_tier: "Quick"` with all T3 citations, inform user: "**This is a docs-only skill.** Drift detection compares against upstream documentation, not source code. Re-run `@Ferris US` to re-fetch documentation URLs and detect content changes." Recommend update-skill instead.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

**If user provides skill name (not full path) — version-aware path resolution (see `knowledge/version-paths.md`):**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill_name}/{active_version}/{skill_name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill_name}/active` — resolve to `{skill_group}/active/{skill_name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill_name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}`

**If user provides full path:**
- Use as provided

**Validate:** Check that `SKILL.md` exists at the resolved path.
- If missing → "Skill not found at `{resolved_skill_package}`. Check the path and try again."
- If found → Continue

### 2. Load Forge Tier

Load `{sidecar_path}/forge-tier.yaml` to detect available tools.

**If file missing:**
- "Setup-forge has not been run. Cannot determine tool availability. Run `[SF] Setup Forge` first."
- HALT workflow

**If found:**
- Extract tier level: Quick / Forge / Forge+ / Deep
- Extract available tools: gh_bridge, ast_bridge, qmd_bridge — see `knowledge/tool-resolution.md` for concrete tool resolution per IDE

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

### 3. Load Skill Artifacts

Load the following from the skill directory:

**Required:**
- `SKILL.md` — The skill document to audit
- `metadata.json` — Skill metadata (version, created date, export count)

**Extract from metadata.json:**
- `name`, `version`, `generation_date`, `confidence_tier` used during creation
- `source_root` — Resolved source code path used during extraction

**Detect split-body state:** If a `references/` directory exists and SKILL.md's `## Full` headings are absent or stubs, this is a split-body skill. Flag `split_body: true` in the baseline so downstream steps (especially semantic diff in step-04) know to also read `references/*.md` for complete content comparison.

### 4. Load Provenance Map

Search for provenance map at `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json` (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`:

**If found:**
- Load and extract: export list, file mappings, extraction timestamps, confidence tiers
- Record provenance map age (days since last extraction)

**If missing at both paths:**
- "No provenance map found for `{skill_name}`. This skill may not have been created by create-skill."
- "**Degraded mode available:** I can perform text-based comparison without provenance data. Findings will have T1-low confidence."
- "**[D]egraded mode** — proceed with text-diff only"
- "**[X]** — abort audit"
- Wait for user selection. If D, set `degraded_mode: true`. If X, halt workflow.

### Stack Skill Detection

After loading provenance-map.json, detect skill type:
- If `provenance_version` is `"2.0"` and `skill_type` is `"stack"`: set `{is_stack_skill}` = true
- If provenance-map has top-level `libraries` key (v1 stack format): set `{is_stack_skill}` = true, `{legacy_stack_provenance}` = true
- Otherwise: `{is_stack_skill}` = false

If `{is_stack_skill}` is true and `constituents` array is present (compose-mode stack):
- For each constituent, compute the current metadata hash: read `{constituent.skill_path}/active/{constituent.skill_name}/metadata.json` and compute SHA-256
- Compare against `constituent.metadata_hash`
- Flag any mismatches as **constituent drift** with severity HIGH
- Record constituent freshness results for the report

If `{legacy_stack_provenance}` is true: log a note that this stack uses v1 provenance format with reduced audit depth (library-level only, no per-export verification).

### 5. Resolve Source Path

**If provenance map loaded:**
- Use `source_root` from provenance map as source code path
- Verify source path still exists and is accessible

**If degraded mode:**
- Ask user: "Please provide the path to the current source code."

**Validate:** Confirm source directory exists and contains expected files.

### 6. Create Drift Report

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Set `stepsCompleted: ['step-01-init']`
- Fill Audit Summary skeleton with loaded baseline data

### 7. Present Baseline Summary (User Gate)

"**Audit Baseline Loaded**

| Field | Value |
|-------|-------|
| **Skill** | {skill_name} v{version} |
| **Created** | {generation_date} |
| **Source** | {source_path} |
| **Forge Tier** | {current_tier} (created at {original_tier}) |
| **Provenance Age** | {days} days since last extraction |
| **Export Count** | {count} exports in provenance map |
| **Mode** | {normal / degraded} |

**Analysis plan based on tier:**
- {Quick: text-diff comparison (T1-low confidence)}
- {Forge: AST structural comparison (T1 confidence)}
- {Forge+: AST structural comparison + CCC-assisted rename detection (T1 confidence)}
- {Deep: AST structural + QMD semantic comparison (T1 + T2 confidence)}

**Ready to begin drift analysis?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Analysis"

#### Menu Handling Logic:

- IF C: Save baseline to {outputFile}, update frontmatter stepsCompleted, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past baseline confirmation"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and the drift report has been created with baseline data populated, will you then load and read fully `{nextStepFile}` to execute and begin source re-indexing.


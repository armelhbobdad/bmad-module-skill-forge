---
nextStepFile: './step-02-detect-mode.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
templateFile: 'templates/test-report-template.md'
sidecarFile: '{sidecar_path}/forge-tier.yaml'
skillsOutputFolder: '{skills_output_folder}'
# frontmatterScript `shared/scripts/skf-validate-frontmatter.py` resolves
# relative to the SKF module root (`_bmad/skf/` when installed, `src/` during
# development), NOT relative to this step file.
frontmatterScript: 'shared/scripts/skf-validate-frontmatter.py'
versionPathsKnowledge: 'knowledge/version-paths.md'
---

# Step 1: Initialize Test

## STEP GOAL:

Discover and validate the target skill, load forge tier state to determine analysis depth, and create the test report document from template.

## Rules

- Focus only on input discovery and validation — do not begin analysis
- Validate all required files exist before proceeding

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Receive Skill Path

If skill path was provided as workflow argument, use it directly.

If no path provided, ask:

"**Which skill would you like to test?**

Provide the skill path or name. I'll search in `{skillsOutputFolder}`.

**Path or name:**"

### 2. Validate Skill Exists (version-aware)

Resolve the skill path using version-aware resolution (see `{versionPathsKnowledge}`):

1. Read `{skillsOutputFolder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skillsOutputFolder}/{skill_name}/{active_version}/{skill_name}/`
3. If not in manifest: check for `active` symlink at `{skillsOutputFolder}/{skill_name}/active` — resolve to `{skill_group}/active/{skill_name}/`
4. If neither: fall back to flat path `{skillsOutputFolder}/{skill_name}/`. If SKILL.md exists at the flat path, auto-migrate per `{versionPathsKnowledge}` migration rules
5. Store the resolved path as `{resolved_skill_package}`

Check that the skill package contains required files:

**Required files:**
- `{resolved_skill_package}/SKILL.md` — the skill documentation
- `{resolved_skill_package}/metadata.json` — skill metadata

**If SKILL.md missing:**
"**Error: SKILL.md not found at `{resolved_skill_package}/SKILL.md`**

This skill has not been created yet. Run the **create-skill** workflow first."

HALT — do not proceed.

**If metadata.json missing:**
"**Warning:** metadata.json not found. Proceeding with limited metadata. Some checks may be skipped."

### 3. Validate Frontmatter Compliance

Run the deterministic frontmatter validator:

```bash
python3 {frontmatterScript} {resolved_skill_package}/SKILL.md --skill-dir-name {skill_name}
```

Where `{frontmatterScript}` resolves from the SKF module root (e.g., `_bmad/skf/shared/scripts/skf-validate-frontmatter.py` installed, or `src/shared/scripts/skf-validate-frontmatter.py` in development).

Parse the JSON output. If `status` is `"fail"` or `"warn"`, display:

"**Warning: SKILL.md frontmatter is non-compliant with agentskills.io specification.**

{list issues from the JSON output}

This skill will fail `npx skills add` and `npx skill-check check`. Consider fixing frontmatter before proceeding (run `npx skill-check check <skill-dir> --fix` to auto-fix deterministic issues)."

Log each issue as a pre-check finding. Continue with testing — frontmatter issues will be reported in the gap report alongside coverage/coherence findings.

**If the script is unavailable**, perform the checks manually: frontmatter delimiters present, `name` is lowercase alphanumeric + hyphens (1-64 chars) matching the directory name, `description` is non-empty (1-1024 chars), no unknown fields (only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` permitted).

### 4. Load Forge Tier State

Read `{sidecarFile}` to determine available analysis depth.

**If forge-tier.yaml exists:**
- Read `tier` value (Quick, Forge, Forge+, or Deep)
- Read tool availability flags (ast_grep, gh_cli, qmd)

**If forge-tier.yaml missing:**
"**Cannot proceed.** forge-tier.yaml not found at `{sidecarFile}`. Please run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."

HALT — do not proceed.

### 4b. Apply Tier Override (if set)

Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), update `detected_tier` to the override value for use in subsequent steps and output documents.

### 5. Load Skill Metadata

Read `metadata.json` to extract:
- `name` — display name
- `skill_type` — single or stack (needed for mode detection)
- `source_path` — path to source code (if present)
- `generation_date` — when skill was generated
- `confidence_tier` — tier used during creation

If source path override was provided as optional input, use that instead.

### 6. Create Output Document

Create `{outputFile}` from `{templateFile}` with initial frontmatter:

```yaml
---
workflowType: 'test-skill'
skillName: '{skill_name}'
skillDir: '{skill_path}'
testMode: ''
forgeTier: '{detected_tier}'
testResult: ''
score: ''
threshold: ''
analysisConfidence: ''
testDate: '{current_date}'
stepsCompleted: ['step-01-init']
nextWorkflow: ''
---
```

### 7. Report Initialization Status

"**Test initialization complete.**

**Skill:** {skill_name}
**Path:** {skill_path}
**Type:** {skill_type}
**Forge Tier:** {detected_tier}
**Source:** {source_path}

**Proceeding to mode detection...**"

### 8. Auto-Proceed

Display: "**Proceeding to mode detection...**"

#### Menu Handling Logic:

- After initialization is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices
- Proceed directly to next step after setup

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all required files are validated, forge tier is loaded, output document is created, and initialization status is reported, will you then load and read fully `{nextStepFile}` to execute mode detection.


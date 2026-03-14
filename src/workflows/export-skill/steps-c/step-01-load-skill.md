---
name: 'step-01-load-skill'
description: 'Load skill artifacts and validate spec compliance before export'

nextStepFile: './step-02-package.md'
---

# Step 1: Load Skill

## STEP GOAL:

To load the target skill's artifacts, validate they meet agentskills.io spec compliance, parse export flags, and confirm with the user before proceeding to packaging.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER proceed without user confirmation of the loaded skill
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a delivery and packaging specialist in Ferris Delivery mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Precise and efficient — validate thoroughly, report clearly
- ✅ User brings the skill path and export preferences

### Step-Specific Rules:

- 🎯 Focus only on loading, validating, and confirming the skill
- 🚫 FORBIDDEN to modify any skill files — this is read-only
- 🚫 FORBIDDEN to write any output files yet — packaging starts in step-02
- 💬 Present a clear summary of what was found for user confirmation

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Hold all loaded data in context for subsequent steps
- 📖 Validate against agentskills.io spec requirements
- 🚫 Hard halt if required files are missing — do not proceed with incomplete skill

## CONTEXT BOUNDARIES:

- Available: SKF module config (skills_output_folder, forge_data_folder)
- Focus: Skill discovery, loading, and validation
- Limits: Read-only — no file writes in this step
- Dependencies: Skill must have been created by create-skill or update-skill

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Parse Export Arguments

"**Starting skill export...**"

Determine the skill to export and any flags:

**Skill Path Discovery:**
- If user provided a skill name or path as argument, use that
- If not provided, search `{skills_output_folder}/*/SKILL.md` for available skills
- If multiple skills found, present list and ask user to select
- If no skills found, halt: "No skills found in {skills_output_folder}/. Run create-skill first."

**Flag Parsing:**
- `--platform` flag: Check if provided (claude/cursor/copilot). Default: `claude`
- `--dry-run` flag: Check if provided. Default: `false`

"**Skill:** {skill-name}
**Platform:** {platform} ({target-file})
**Dry Run:** {yes/no}"

### 2. Load and Validate Skill Artifacts

Load all files from the skill directory `{skills_output_folder}/{skill-name}/`:

**Required Files (hard halt if missing):**
- `SKILL.md` — The main skill document
- `metadata.json` — Machine-readable skill metadata

**Optional Files (note presence):**
- `references/` — Progressive disclosure directory
- `context-snippet.md` — Existing snippet (will be regenerated)

**Validation Checks:**
1. `SKILL.md` exists and is non-empty
2. `metadata.json` exists and is valid JSON
3. `metadata.json` contains required fields: `name`, `version`, `skill_type`, `source_authority`, `exports`, `generation_date`, `confidence_tier`
4. `metadata.json.exports` is a non-empty array (warn if empty — graceful handling)

**If any required validation fails:**
"**Export cannot proceed.** Missing or invalid: {list failures}
Run create-skill to generate a complete skill first."

### 3. Read Skill Metadata

Extract from `metadata.json`:
- `name` — Skill display name
- `skill_type` — `single` or `stack`
- `source_authority` — `official`, `internal`, or `community`
- `exports` — Array of exported functions/types
- `generation_date` — When the skill was last generated
- `confidence_tier` — Quick/Forge/Deep

**For stack skills, also extract:**
- `components` — Array of dependencies with versions
- `integrations` — Array of co-import patterns

### 4. Check Forge Configuration

Load `{sidecar_path}/preferences.yaml` (if exists):
- Check `passive_context` setting
- If `passive_context: false` — note that steps 03-04 (snippet + context update) will be skipped

### 4b. Check Test Report (Quality Gate)

Search for a test report at `{output_folder}/test-report-{skill-name}.md`:

**If test report found:**
- Read frontmatter `testResult` and `score`
- If `testResult: fail`: warn: "**Warning:** This skill failed its last test (score: {score}%). Consider running `@Ferris TS` and addressing gaps before export."
- If `testResult: pass`: note: "Last test: **PASS** ({score}%)"

**If no test report found:**
- Warn: "**Note:** No test report found for this skill. Consider running `@Ferris TS` before export to verify completeness."

Continue to step 5 regardless — this is advisory, not blocking.

### 5. Present Skill Summary

"**Skill loaded and validated.**

| Field | Value |
|-------|-------|
| **Name** | {name} |
| **Type** | {skill_type} |
| **Authority** | {source_authority} |
| **Confidence** | {confidence_tier} |
| **Exports** | {count} functions/types |
| **Generated** | {generation_date} |
| **References** | {count files or 'none'} |

**Export Configuration:**
| Setting | Value |
|---------|-------|
| **Platform** | {platform} → {target-file} |
| **Dry Run** | {yes/no} |
| **Passive Context** | {enabled/disabled} |

**Top Exports:**
{list top 5 exports from metadata}

**Is this the correct skill to export?**"

### 6. Present MENU OPTIONS

Display: "**Select:** [C] Continue to packaging"

#### Menu Handling Logic:

- IF C: Proceed with loaded skill data, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms the correct skill is loaded by selecting 'C' will you load and read fully `{nextStepFile}` to execute packaging.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill path resolved (from argument or discovery)
- All required files loaded and validated
- metadata.json parsed with required fields
- Export flags parsed (platform, dry-run)
- Forge config checked for passive_context
- Clear summary presented to user
- User confirms correct skill

### ❌ SYSTEM FAILURE:

- Proceeding without finding SKILL.md or metadata.json
- Not validating metadata.json fields
- Not checking preferences.yaml for passive_context opt-out
- Proceeding without user confirmation
- Modifying any skill files (read-only step)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

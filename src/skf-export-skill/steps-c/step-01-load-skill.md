---
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

**Skill Path Discovery (version-aware — see [knowledge/version-paths.md](../../knowledge/version-paths.md)):**
- If user provided a skill name or path as argument, use that
- If not provided, discover available skills using the export manifest:
  1. Read `{skills_output_folder}/.export-manifest.json` — list skill names from `exports`
  2. For each skill group directory in `{skills_output_folder}/`, check for `{skill_group}/active/{skill-name}/SKILL.md`
  3. If neither manifest nor `active` symlink yields results, fall back to flat path: `{skills_output_folder}/{skill-name}/SKILL.md`
- If multiple skills found, present list and ask user to select
- If no skills found, halt: "No skills found in {skills_output_folder}/. Run create-skill first."

**Flag Parsing:**
- `--platform` flag: Check if explicitly provided (claude/cursor/copilot)
- `--dry-run` flag: Check if provided. Default: `false`

**Platform Resolution:**

If `--platform` is explicitly provided, use that single platform as the sole target. If other IDEs are configured in config.yaml, emit a note: "**Note:** Exporting to {platform} only. config.yaml also lists: {other-ides}. Run without `--platform` to export to all configured IDEs."

If `--platform` is NOT provided, read the `ides` list from config.yaml and map each IDE to a target platform. Every IDE the installer offers has an explicit mapping — no silent skips.

| config.yaml IDE value | Platform | Rationale |
|----------------------|----------|-----------|
| `claude-code` | `claude` | native — reads `CLAUDE.md` and `.claude/skills/` |
| `cursor` | `cursor` | native — reads `.cursorrules` and `.cursor/skills/` |
| `github-copilot` | `copilot` | native — reads `AGENTS.md` and `.agents/skills/` |
| `codex` | `copilot` | OpenAI Codex reads `AGENTS.md` (same convention as copilot) |
| `cline` | `copilot` | uses `AGENTS.md` as a fallback context file |
| `roo` | `copilot` | uses `AGENTS.md` as a fallback context file |
| `windsurf` | `copilot` | uses `AGENTS.md` as a fallback context file |
| `other` | `copilot` | generic AGENTS.md fallback |
| Any other value | `copilot` | warn: "Unknown IDE '{value}' in config.yaml — defaulting to copilot (AGENTS.md)" |

When the same platform is produced by multiple IDE entries (e.g. both `codex` and `cline` map to `copilot`), deduplicate so each platform appears in `target_platforms` only once. Report the deduplication: "Multiple IDEs target the same platform — exporting to {platform} once."

**Missing-key handling:** If the `ides` key is absent from config.yaml (older installation or manually edited file), treat it as an empty list.

- If mapping produces one or more platforms (after dedup), store as `target_platforms` list
- If mapping produces zero platforms (empty ides list and no recognized entries), fall back to `["copilot"]` with note: "No IDEs configured in config.yaml — defaulting to copilot (AGENTS.md / .agents/skills/)."

"**Skill:** {skill-name}
**Platform(s):** {platform-list} ({target-file-list})
**Dry Run:** {yes/no}"

### 2. Load and Validate Skill Artifacts

Resolve the skill's versioned path before loading artifacts:

1. Read `{skills_output_folder}/.export-manifest.json` and look up `{skill-name}` in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill-name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading

Load all files from `{resolved_skill_package}`:

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
- `confidence_tier` — Quick/Forge/Forge+/Deep

**For stack skills, also extract:**
- `components` — Array of dependencies with versions
- `integrations` — Array of co-import patterns

### 4. Check Forge Configuration

Load `{sidecar_path}/preferences.yaml` (if exists):
- Check `passive_context` setting
- If `passive_context: false` — note that steps 03-04 (snippet + context update) will be skipped

### 4b. Check Test Report (Quality Gate)

Search for a test report at `{forge_data_folder}/{skill_name}/{active_version}/test-report-{skill_name}.md` (i.e., `{forge_version}/test-report-{skill_name}.md`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/test-report-{skill_name}.md`:

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
| **Platform(s)** | {platform-list} → {target-file-list} |
| **Explicit --platform** | {yes (user-specified) / no (from config.yaml)} |
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
- config.yaml ides list consumed for multi-platform resolution when --platform not provided
- Forge config checked for passive_context
- Clear summary presented to user
- User confirms correct skill

### ❌ SYSTEM FAILURE:

- Proceeding without finding SKILL.md or metadata.json
- Not validating metadata.json fields
- Not checking preferences.yaml for passive_context opt-out
- Proceeding without user confirmation
- Ignoring config.yaml ides list when no --platform flag is provided
- Modifying any skill files (read-only step)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

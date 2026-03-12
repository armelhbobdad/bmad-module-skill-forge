---
name: 'step-05-validate'
description: 'Validate compiled SKILL.md, context-snippet, and metadata against agentskills.io spec'

nextStepFile: './step-06-write.md'
---

# Step 5: Validate

## STEP GOAL:

To validate the compiled SKILL.md, context-snippet.md, and metadata.json against the agentskills.io specification at community tier. Report any gaps or issues. This is advisory validation — issues are reported but do not block output.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a rapid skill compiler performing quality checks
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Community-tier validation — lighter than official requirements
- ✅ Report issues honestly but don't block output

### Step-Specific Rules:

- 🎯 Focus only on validating the compiled output
- 🚫 FORBIDDEN to modify the compiled content — report issues only
- 💬 Approach: Check each requirement, report findings, proceed
- 📋 Validation failures are advisory — user can proceed regardless

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Set state: validation_result (pass/fail, issues_list)
- 📖 Check against community-tier requirements
- 🚫 Do not block output on validation issues

## CONTEXT BOUNDARIES:

- Previous step provided: skill_content (SKILL.md), context_snippet, metadata_json
- Focus: validation only, not modification
- Community tier has lighter requirements than official
- Dependencies: compiled output from step-04

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Validate SKILL.md Frontmatter (agentskills.io Compliance)

Check that SKILL.md has valid YAML frontmatter — this is REQUIRED for ecosystem compatibility:

- [ ] **Frontmatter present** — file starts with `---` delimiter and has closing `---`
- [ ] **`name` field** — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] **`name` matches directory** — frontmatter `name` matches the skill output directory name
- [ ] **`description` field** — present, non-empty, 1-1024 characters
- [ ] **No unknown fields** — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted

**For each violation, log an issue.** Missing frontmatter or missing required fields are high-severity issues — skills without valid frontmatter will fail `npx skills add` and `skills-ref validate`.

### 2. Validate SKILL.md Body Structure

Check that SKILL.md has these required sections populated:

- [ ] **Overview section** present with package name, repo, language, authority
- [ ] **Description section** present with non-empty content
- [ ] **Key Exports section** present (may be empty if confidence is low)
- [ ] **Usage Patterns section** present (may have README fallback)

**For each missing or empty required section, log an issue.**

### 3. Validate Context Snippet Format

Check context-snippet.md format compliance:

- [ ] **Two-line format** — first line has skill name and exports, second line has path pointer
- [ ] **First line** matches pattern: `{name}: {exports list}`
- [ ] **Second line** matches pattern: `  → {path}/SKILL.md`
- [ ] **Approximate token count** is ~30 tokens or less

**If format is wrong, log an issue.**

### 4. Validate Metadata JSON

Check metadata.json has required fields:

- [ ] `name` — present, non-empty
- [ ] `version` — present (should be "0.1.0")
- [ ] `source_authority` — must be "community"
- [ ] `source_repo` — present, valid GitHub URL
- [ ] `language` — present, non-empty
- [ ] `generated_by` — must be "quick-skill"
- [ ] `generated_date` — present
- [ ] `exports_count` — present, number
- [ ] `confidence` — present

**For each missing or invalid field, log an issue.**

### 5. Report Validation Results

"**Validation complete:**

**SKILL.md:** {pass/issues found}
{list any issues}

**context-snippet.md:** {pass/issues found}
{list any issues}

**metadata.json:** {pass/issues found}
{list any issues}

**Overall:** {pass / N issues found}

{If issues found:}
These issues are advisory for community-tier skills. You can proceed to write output or go back to adjust.

**Proceeding to write output...**"

Set `validation_result` with pass/fail status and issues list.

### 6. Auto-Proceed to Write

#### Menu Handling Logic:

- After validation report, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step — validation is advisory
- Proceed directly to write step after reporting results

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN validation checks are complete and results reported will you load and read fully `{nextStepFile}` to execute file writing.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All three outputs validated against requirements
- Issues reported clearly with specific details
- Community-tier validation applied (not official-tier strictness)
- validation_result set with pass/fail and issues list
- Auto-proceeding to write step

### ❌ SYSTEM FAILURE:

- Modifying compiled content instead of just reporting
- Blocking output on validation issues (advisory only)
- Skipping validation checks
- Not reporting found issues

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

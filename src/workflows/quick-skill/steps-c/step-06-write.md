---
name: 'step-06-write'
description: 'Write output files to skills folder and display completion summary'
nextStepFile: '../../shared/health-check.md'
---

# Step 6: Write Output

## STEP GOAL:

To write the compiled SKILL.md, context-snippet.md, and metadata.json to the skills output folder and display a completion summary with next step recommendations.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a rapid skill compiler delivering the final output
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Precision file writing — correct paths, correct content
- ✅ This is the final step — deliver cleanly and recommend next actions

### Step-Specific Rules:

- 🎯 Focus only on writing files and displaying summary
- 🚫 FORBIDDEN to modify content — write exactly what was compiled
- 💬 Approach: Create directory, write files, confirm, summarize
- 📋 If write fails, hard halt with error details

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Write three files to `{skill_package}` and create the `active` symlink
- 📖 File I/O required for directory creation and file writing
- 🚫 This is the final step — no next step to load

## CONTEXT BOUNDARIES:

- Previous steps provided: skill_content, context_snippet, metadata_json, validation_result
- Also available: resolved_url, repo_name, language, skills_output_folder
- Focus: file writing and completion only
- This is the FINAL step — workflow ends here
- Path resolution: See `knowledge/version-paths.md` for canonical path templates. Quick-skill uses `{repo_name}` as the skill name and defaults `{version}` to `1.0.0` if not detected from the extraction inventory

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Create Output Directory

Resolve `{version}` from the extraction inventory's detected version, defaulting to `1.0.0` if not detected. Create the skill output directories:

```
{skill_group}                          # {skills_output_folder}/{repo_name}/
{skill_package}                        # {skills_output_folder}/{repo_name}/{version}/{repo_name}/
```

If `{skill_package}` already exists, confirm with user before overwriting:

"**Directory `{skill_package}` already exists.** Overwrite existing files? [Y/N]"

- **If user selects Y:** Proceed to section 2.
- **If user selects N:** Halt with: "Overwrite cancelled. Existing skill preserved. Run [QS] with a different skill name or remove the existing directory manually."

### 2. Write SKILL.md

Write the compiled SKILL.md content to:

```
{skill_package}/SKILL.md
```

Confirm: "Written: SKILL.md"

### 3. Write context-snippet.md

Write the context snippet to:

```
{skill_package}/context-snippet.md
```

Confirm: "Written: context-snippet.md"

### 4. Write metadata.json

Write the metadata JSON to:

```
{skill_package}/metadata.json
```

Confirm: "Written: metadata.json"

### 4b. Create Active Symlink

Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}`:

```
{skill_group}/active -> {version}
```

If the symlink already exists, remove it first and recreate.

Confirm: "Symlink: {skill_group}/active -> {version}"

### 5. Handle Write Failures

**If any file write fails — HARD HALT:**

"**Write failed:** Could not write to `{file_path}`.

Error: {error details}

Please check:
- Does the output directory exist and is it writable?
- Is there sufficient disk space?
- Are there permission issues?"

### 6. Display Completion Summary

"**Quick Skill complete.**

**Skill:** {repo_name} v{version}
**Language:** {language}
**Source:** {resolved_url}
**Authority:** community
**Confidence:** {extraction confidence}

**Files written:**
- `{skill_package}/SKILL.md`
- `{skill_package}/context-snippet.md`
- `{skill_package}/metadata.json`
- `{skill_group}/active` -> `{version}`

**Exports documented:** {count}
**Validation:** {pass / N issues (advisory)}

---

**Recommended next steps:**

1. **test-skill** (advisory) — Run cognitive completeness verification on the generated skill
2. **export-skill** — Package and distribute the skill with platform-aware context injection

**Note:** This is a best-effort community skill. For deeper analysis with AST-verified exports and provenance tracking, use the full **create-skill** workflow with a skill brief."

### 7. Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Output directory created (or overwrite confirmed) with version-nested structure
- All three files written successfully to {skill_package}
- Active symlink created at {skill_group}/active -> {version}
- Completion summary displayed with file paths
- Next step recommendations provided
- Workflow ends cleanly

### ❌ SYSTEM FAILURE:

- Modifying content during write (write exactly what was compiled)
- Not handling write failures with hard halt
- Not displaying completion summary
- Attempting to load a next step (this is final)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

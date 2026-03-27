---
name: 'step-06-write'
description: 'Write output files to skills folder and display completion summary'
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
- 💾 Write three files to {skills_output_folder}/{repo_name}/
- 📖 File I/O required for directory creation and file writing
- 🚫 This is the final step — no next step to load

## CONTEXT BOUNDARIES:

- Previous steps provided: skill_content, context_snippet, metadata_json, validation_result
- Also available: resolved_url, repo_name, language, skills_output_folder
- Focus: file writing and completion only
- This is the FINAL step — workflow ends here

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Create Output Directory

Create the skill output directory:

```
{skills_output_folder}/{repo_name}/
```

If directory already exists, confirm with user before overwriting:

"**Directory `{skills_output_folder}/{repo_name}/` already exists.** Overwrite existing files? [Y/N]"

- **If user selects Y:** Proceed to section 2.
- **If user selects N:** Halt with: "Overwrite cancelled. Existing skill preserved. Run [QS] with a different skill name or remove the existing directory manually."

### 2. Write SKILL.md

Write the compiled SKILL.md content to:

```
{skills_output_folder}/{repo_name}/SKILL.md
```

Confirm: "Written: SKILL.md"

### 3. Write context-snippet.md

Write the context snippet to:

```
{skills_output_folder}/{repo_name}/context-snippet.md
```

Confirm: "Written: context-snippet.md"

### 4. Write metadata.json

Write the metadata JSON to:

```
{skills_output_folder}/{repo_name}/metadata.json
```

Confirm: "Written: metadata.json"

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

**Skill:** {repo_name}
**Language:** {language}
**Source:** {resolved_url}
**Authority:** community
**Confidence:** {extraction confidence}

**Files written:**
- `{skills_output_folder}/{repo_name}/SKILL.md`
- `{skills_output_folder}/{repo_name}/context-snippet.md`
- `{skills_output_folder}/{repo_name}/metadata.json`

**Exports documented:** {count}
**Validation:** {pass / N issues (advisory)}

---

**Recommended next steps:**

1. **test-skill** (advisory) — Run cognitive completeness verification on the generated skill
2. **export-skill** — Package and distribute the skill with platform-aware context injection

**Note:** This is a best-effort community skill. For deeper analysis with AST-verified exports and provenance tracking, use the full **create-skill** workflow with a skill brief."

### 7. End Workflow

This is the final step. The workflow is complete.

No next step to load. Session ends here.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Output directory created (or overwrite confirmed)
- All three files written successfully
- Completion summary displayed with file paths
- Next step recommendations provided
- Workflow ends cleanly

### ❌ SYSTEM FAILURE:

- Modifying content during write (write exactly what was compiled)
- Not handling write failures with hard halt
- Not displaying completion summary
- Attempting to load a next step (this is final)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

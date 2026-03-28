---
name: 'step-05-write-brief'
description: 'Generate and write skill-brief.yaml to the forge data folder'

briefSchemaFile: '../data/skill-brief-schema.md'
---

# Step 5: Write Brief

## STEP GOAL:

To generate the complete skill-brief.yaml from the approved brief data and write it to the forge data folder, completing the brief-skill workflow.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a skill brief generator in Ferris Architect mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Generate output precisely matching the schema — no creative embellishment
- ✅ This is the final step — deliver clean, validated output

### Step-Specific Rules:

- 🎯 Focus only on writing the file — all decisions have been made
- 🚫 FORBIDDEN to change any field values without user request — the brief was already approved
- 💬 Approach: Prescriptive — generate exact YAML matching the schema template
- 📋 Create the output directory if it doesn't exist

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Write skill-brief.yaml to {forge_data_folder}/{skill-name}/
- 📖 This is the final step — mark workflow complete
- 🚫 FORBIDDEN to modify approved field values

## CONTEXT BOUNDARIES:

- Available context: Complete approved brief data from steps 01-04
- Focus: File generation and writing
- Limits: No field changes — write exactly what was approved
- Dependencies: Explicit user approval from step 04

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Schema Template

Load `{briefSchemaFile}` to reference the YAML template structure.

### 2. Create Output Directory

Create the directory `{forge_data_folder}/{skill-name}/` if it doesn't already exist.

If `{forge_data_folder}` is not set or doesn't exist:
- Fall back to `{output_folder}/forge-data/{skill-name}/`
- Inform user: "**Note:** forge_data_folder not configured. Writing to {output_folder}/forge-data/{skill-name}/ instead."

### 3. Generate skill-brief.yaml

Generate the YAML file using the approved field values and the schema template:

```yaml
---
name: "{approved skill name}"
version: "{detected source version or 1.0.0}"
source_type: "{source or docs-only}"
source_repo: "{approved source repo or doc site URL}"
language: "{approved language}"
description: "{approved description}"
forge_tier: "{approved forge tier}"
created: "{current date}"
created_by: "{user_name}"
scope:
  type: "{approved scope type}"
  include:
    - "{approved include patterns}"
  exclude:
    - "{approved exclude patterns}"
  notes: "{approved scope notes or empty string}"
---
```

**Conditional optional field inclusion:**

**If `source_type: "docs-only"` OR supplemental `doc_urls` were collected:**
Include the `doc_urls` array (uncommented) in the generated YAML:
```yaml
doc_urls:
  - url: "{documentation URL}"
    label: "{page label}"
```
When `source_type: "docs-only"`: `doc_urls` is required (at least one entry), `source_repo` may be set to the doc site URL for reference or omitted.

**If `scripts_intent` was collected and is not the default `"detect"`:**
Include the `scripts_intent` field (uncommented):
```yaml
scripts_intent: "{none or description}"
```

**If `assets_intent` was collected and is not the default `"detect"`:**
Include the `assets_intent` field (uncommented):
```yaml
assets_intent: "{none or description}"
```

**Always include** `source_authority` (default: `"community"`, forced to `"community"` when `source_type: "docs-only"`):
```yaml
source_authority: "{official|community|internal}"
```

### 4. Write the File

Write the generated YAML to `{forge_data_folder}/{skill-name}/skill-brief.yaml`.

If write fails: **HALT** — "**Error:** Failed to write skill-brief.yaml. Please check that the directory is writable and try again."

### 5. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:**

Index the skill brief into a QMD collection so that portfolio-level searches can find existing briefs and avoid duplicate skill creation across large monorepos.

**Collection creation:**

Create a QMD collection targeting only the brief file:
```bash
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

If collection already exists (re-briefing): remove and recreate for atomic replace:
```bash
qmd collection remove {skill-name}-brief
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

**Embed verification:**

After `qmd embed` completes, verify the collection was embedded:
- Run `qmd status` or `qmd collection list` and confirm `{skill-name}-brief` shows document count > 0
- If verification succeeds: proceed to registry update normally
- If verification fails: log warning "QMD embed verification failed for {skill-name}-brief — collection may not be searchable yet", still proceed to registry update but add `status: "pending"` field to the registry entry

**Registry update:**

Read `{sidecar_path}/forge-tier.yaml` and update the `qmd_collections` array.

If an entry with `name: "{skill-name}-brief"` already exists, replace it. Otherwise, append:

```yaml
  - name: "{skill-name}-brief"
    type: "brief"
    source_workflow: "brief-skill"
    skill_name: "{skill-name}"
    created_at: "{current ISO date}"
    # status: "pending"    # Added only when embed verification fails
```

Write the updated forge-tier.yaml.

**Error handling:**
- If QMD collection creation fails: log the error. Do NOT fail the workflow — the brief file was already written successfully.
- If forge-tier.yaml update fails: log the error, continue.

**IF forge tier is NOT Deep:** Skip this section silently. No messaging.

### 6. Display Success Summary

"**Skill brief written successfully.**

---

**File:** `{forge_data_folder}/{skill-name}/skill-brief.yaml`
**Skill:** {name}
**Language:** {language}
**Scope:** {scope type}
**Forge Tier:** {forge tier}

---

## Next Steps

Your skill brief is ready. To compile the actual skill from this brief, run:

**create-skill** — Reads your skill-brief.yaml and compiles a complete SKILL.md with AST-backed analysis.

After compilation, you can:
- **test-skill** — Validate the compiled skill
- **export-skill** — Package the skill for distribution

---

**Brief-skill workflow complete.**"

### 7. End Workflow

This is the final step. No next step file to load. The workflow is complete.

## CRITICAL STEP COMPLETION NOTE

This is the FINAL step of the brief-skill workflow. After writing the file and displaying the success summary, the workflow ends.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Schema loaded for template reference
- Output directory created (or fallback used with notification)
- skill-brief.yaml generated with all required fields matching approved values
- File written successfully to correct location
- Deep tier: QMD collection `{skill-name}-brief` created/updated and registered in forge-tier.yaml
- Non-Deep tier: QMD indexing skipped silently
- Success summary displayed with next steps recommendation
- Workflow marked as complete

### ❌ SYSTEM FAILURE:

- Modifying approved field values without user request
- Writing to wrong location
- Missing required fields in generated YAML
- Not creating output directory before writing
- Not displaying next steps recommendation
- Not handling write failure gracefully
- Failing the workflow due to QMD indexing errors (should degrade gracefully)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. QMD indexing failures never block the workflow.

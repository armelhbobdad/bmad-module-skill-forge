---
name: 'step-04-compile'
description: 'Assemble best-effort SKILL.md, context-snippet.md, and metadata.json from extraction inventory'

nextStepFile: './step-05-validate.md'
skillTemplateData: '../data/skill-template.md'
---

# Step 4: Compile

## STEP GOAL:

To assemble the best-effort SKILL.md document, context-snippet.md in Vercel-aligned indexed format, and metadata.json with `source_authority: community` from the extraction inventory. Present compiled output for review before validation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a rapid skill compiler assembling output documents
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Best-effort quality — populate what's available, mark gaps honestly
- ✅ Follow template structure exactly from {skillTemplateData}

### Step-Specific Rules:

- 🎯 Focus only on assembling the three output documents
- 🚫 FORBIDDEN to write files to disk — that's step-06
- 💬 Approach: Load template, populate from inventory, present for review
- 📋 Mark any sections with insufficient data as best-effort

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Set state: skill_content, context_snippet, metadata_json
- 📖 Load {skillTemplateData} for section structure and format specs
- 🚫 Do not write files — only assemble content in memory

## CONTEXT BOUNDARIES:

- Previous step provided: extraction_inventory (exports, description, manifest_data, confidence)
- Also available: resolved_url, repo_name, language, scope_hint
- Focus: compilation and assembly only
- This step presents output for review — user gets a checkpoint before validation

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Skill Template

Load {skillTemplateData} to understand:
- SKILL.md required and optional sections
- context-snippet.md Vercel-aligned indexed format
- metadata.json field requirements

### 2. Assemble SKILL.md

Using the template structure, populate each section from extraction_inventory:

**Frontmatter (REQUIRED — agentskills.io compliance):**

The SKILL.md MUST begin with YAML frontmatter:

```yaml
---
name: {skill_name}
description: >
  {Trigger-optimized description from extraction_inventory.description.
  1-1024 chars. Include what it does, when to use it, and what NOT to use it for.}
---
```

**Frontmatter rules:**
- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name. Prefer gerund form (`processing-pdfs`) for clarity.
- `description`: non-empty, max 1024 chars, optimized for agent discovery. MUST use third-person voice ("Processes..." not "I can..." or "You can...").
- No other frontmatter fields — only `name` and `description` for community skills

**Required sections (after frontmatter):**
- **Overview:** Package name, repository, language, source authority, generation date
- **Description:** From extraction_inventory.description (README-derived)
- **Key Exports:** From extraction_inventory.exports — list each with name, type, brief description
- **Usage Patterns:** From extraction_inventory.usage_patterns (README examples)

**Optional sections (include when data available):**
- **Configuration:** If configuration options were found in source
- **Dependencies:** Key dependencies from manifest
- **Notes:** Caveats, limitations, extraction confidence level
- **Scripts & Assets Note** (if source contains `scripts/`, `bin/`, `assets/`, `templates/`, or `schemas/` directories): "This package may include scripts and assets. Run create-skill for full extraction with provenance tracking."

**If confidence is low:**
- Include a note: "This skill was generated with limited source data. Consider running create-skill for a more thorough compilation."

### 3. Generate Context Snippet

Create context-snippet.md in Vercel-aligned indexed format (~80-120 tokens):

```
[{skill_name} v{version}]|root: skills/{skill_name}/
|IMPORTANT: {skill_name} v{version} — read SKILL.md before writing {skill_name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top-5 exports with () for functions}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

**If fewer than 5 exports:** Use all available exports.
**If no exports:** Omit the api line.
**If no gotchas known:** Omit the gotchas line.

### 4. Generate Metadata JSON

Generate metadata.json following the exact structure defined in {skillTemplateData} metadata.json section. Populate fields from extraction_inventory:

```json
{
  "name": "{skill_name}",
  "version": "{extraction_inventory.version or 1.0.0}",
  "description": "{brief description of the skill}",
  "skill_type": "single",
  "source_authority": "community",
  "source_repo": "{resolved_url}",
  "source_root": "{resolved_source_path}",
  "source_commit": "{commit_sha_if_available}",
  "source_package": "{package_name from manifest}",
  "language": "{language}",
  "generated_by": "quick-skill",
  "generation_date": "{current ISO date}",
  "confidence_tier": "Quick",
  "spec_version": "1.3",
  "exports": ["{export_1}", "{export_2}"],
  "confidence_distribution": {
    "t1": 0,
    "t1_low": "{number of exports found — must be integer, not string}",
    "t2": 0,
    "t3": 0
  },
  "tool_versions": {
    "ast_grep": null,
    "qmd": null,
    "skf": "{skf_version}"   // Resolution chain: _bmad/skf/package.json → npm require → _bmad/skf/VERSION → "unknown"
  },
  "stats": {
    "exports_documented": "{number of exports found}",
    "exports_public_api": "{number of exports found}",
    "exports_internal": 0,
    "exports_total": "{number of exports found}",
    "public_api_coverage": 1.0,
    "total_coverage": 1.0,
    "scripts_count": 0,
    "assets_count": 0
  },
  "dependencies": [],
  "compatibility": "{semver-range or null}"
}
```

### 5. Present Compiled Output for Review

"**Compilation complete. Review before validation:**

---

**SKILL.md Preview:**

{Display the full assembled SKILL.md content}

---

**context-snippet.md:**

{Display the snippet}

---

**metadata.json:**

{Display the JSON}

---

**Extraction confidence:** {confidence}
**Exports documented:** {count}

Review the output above. When ready, continue to validation."

### 6. Present MENU OPTIONS

Display: **Select:** [C] Continue to Validation

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: Help user adjust compiled output, then redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting compiled output
- ONLY proceed to validation when user selects 'C'
- User can request changes to the compiled output before proceeding

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user reviews the compiled output and selects 'C' will you load and read fully `{nextStepFile}` to execute validation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- SKILL.md assembled with all available sections populated
- context-snippet.md generated in correct Vercel-aligned indexed format
- metadata.json generated with source_authority: community
- Compiled output presented for user review
- User confirms readiness before proceeding to validation

### ❌ SYSTEM FAILURE:

- Writing files to disk (that's step-06)
- Skipping the review checkpoint
- Not following template structure from {skillTemplateData}
- Hallucinating exports or data not in extraction_inventory

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

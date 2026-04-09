---
nextStepFile: './step-03-generate-snippet.md'
---

# Step 2: Package

## STEP GOAL:

To assemble and validate an agentskills.io-compliant package structure from the loaded skill artifacts, ensuring all required components are present and properly formatted for distribution.

## Rules

- Focus only on package structure assembly and validation — do not modify SKILL.md content
- Auto-proceed when complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Validate Package Structure

Verify the skill package at `{resolved_skill_package}` (resolved in step-01 via manifest or `active` symlink — see `knowledge/version-paths.md`) contains the expected agentskills.io package layout:

```
{skill_package} = {skills_output_folder}/{skill-name}/{version}/{skill-name}/
├── SKILL.md              ← Required: Active skill document
├── metadata.json         ← Required: Machine-readable metadata
├── context-snippet.md    ← Will be generated/updated in step-03
├── references/           ← Optional: Progressive disclosure
│   ├── {function-a}.md
│   └── {function-b}.md
├── scripts/              ← Optional: Executable automation
└── assets/               ← Optional: Templates, schemas, configs
```

**Check each component:**
1. `SKILL.md` — Verify has frontmatter with `name` field
2. `metadata.json` — Verify required agentskills.io fields:
   - `name` (string, non-empty)
   - `version` (string, semver format preferred)
   - `skill_type` ("single" or "stack")
   - `source_authority` ("official", "internal", or "community")
   - `exports` (array)
   - `generation_date` (ISO date string)
   - `confidence_tier` ("Quick", "Forge", "Forge+", or "Deep")
3. `references/` — If exists, check at least one .md file present
4. `scripts/` — If exists, verify at least one file present and each file referenced in SKILL.md Section 7b exists. Warn for orphaned scripts (present but not referenced).
5. `assets/` — If exists, verify at least one file present and each file referenced in SKILL.md Section 7b exists. Warn for orphaned assets (present but not referenced).

### 2. Validate Metadata Completeness

Check metadata.json for recommended (non-required) fields:

- `description` — Brief skill description
- `source_repo` — Source repository URL
- `language` — Primary language of source code
- `ast_node_count` — Number of AST nodes analyzed
- `tool_versions` — Tools used during generation

**For each missing recommended field:** Note as warning, do not halt.

### 3. Assess Package Readiness

Determine package status:

**READY:** All required files present, all required metadata fields valid
**WARNINGS:** Ready but with missing recommended fields or empty references/
**NOT READY:** Missing required files or required metadata fields (should not reach here — step-01 would have halted)

### 4. Report Package Status

"**Package structure validated.**

**Status:** {READY / WARNINGS}

**Required Components:**
- SKILL.md: ✅
- metadata.json: ✅ ({count} required fields valid)
- references/: {✅ present ({count} files) / ⚠️ not present}

{If warnings:}
**Warnings:**
- {list missing recommended fields}

**Package is ready for snippet generation.**"

### 5. Proceed to Snippet Generation

Display: "**Proceeding to snippet generation...**"

#### Menu Handling Logic:

- After package validation completes, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after validation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN package validation is complete will you load and read fully `{nextStepFile}` to execute snippet generation.


---
name: 'step-06-generate-briefs'
description: 'Generate skill-brief.yaml per confirmed unit, write analysis summary, recommend next workflow'

outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
schemaFile: '../data/skill-brief-schema.md'
---

# Step 6: Generate Briefs

## STEP GOAL:

To generate a valid skill-brief.yaml file for each confirmed unit using the schema, write the files to the forge data folder, append generation results to the analysis report, and recommend the appropriate next workflow for each unit — completing the analyze-source workflow.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a source code analyst and decomposition architect (Ferris Architect mode)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Prescriptive precision — zero-hallucination, every brief field backed by evidence from prior steps
- ✅ This is the GENERATION step — produce files that are immediately consumable by downstream workflows

### Step-Specific Rules:

- 🎯 Generate ONLY for units in confirmed_units — no extras, no omissions
- 🚫 FORBIDDEN to modify recommendations or re-ask for confirmations (that was step 05)
- 💬 Every generated field must trace back to data collected in steps 02-05
- 📋 Validate each brief against the schema before writing

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Write skill-brief.yaml files to `{forge_data_folder}/{unit-name}/`
- 💾 Append "## Generation Results" section to {outputFile}
- 📖 Update stepsCompleted and mark workflow COMPLETE in {outputFile} frontmatter
- 🚫 FORBIDDEN to skip validation of generated briefs

## CONTEXT BOUNDARIES:

- Available: Full report — all sections from steps 02-05, confirmed_units list, stack_skill_candidates
- Focus: YAML generation, file writing, downstream workflow recommendation
- Limits: Do not re-analyze source code — use only data already captured in the report
- Dependencies: step-05-recommend must have populated confirmed_units with at least one entry

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Context

Read {outputFile} completely to obtain:
- `confirmed_units` from frontmatter (names of units approved in step 05)
- `project_paths`, `forge_tier`, `user_name`, `forge_data_folder` from frontmatter
- Recommendation cards from "## Recommendations" section (proposed brief fields per unit)
- Export map and integration data from prior sections

Load {schemaFile} for validation reference.

**Guard clause:** If `confirmed_units` is empty, present:
"**No confirmed units to generate briefs for.** The analysis is complete with no skill briefs produced. Run analyze-source again with different scope or parameters if needed."
Mark workflow complete and halt.

### 2. Generate Skill-Brief YAML Per Unit

For EACH unit in `confirmed_units`, construct a skill-brief.yaml using:

**Field mapping:**

| Field | Source |
|-------|--------|
| name | Confirmed name from step 05 recommendation card |
| version | Auto-detect from source (see schema Version Detection), fall back to `1.0.0` |
| source_repo | `{project_paths[0]}` from frontmatter (or per-unit path if multi-repo) |
| language | Primary language detected in step 03 |
| scope.type | Scope type from step 05 recommendation card |
| scope.include | Include patterns from step 05 recommendation card |
| scope.exclude | Inferred from heuristics (test files, generated code) |
| scope.notes | Rationale from step 05 recommendation card |
| description | Description from step 05 recommendation card |
| forge_tier | `{forge_tier}` from frontmatter |
| created | Current date (ISO format YYYY-MM-DD) |
| created_by | `{user_name}` from frontmatter |

### 3. Validate Each Brief

For each generated brief, check against {schemaFile} validation rules:

1. **Name uniqueness** — no duplicate names within the batch or existing skills
2. **Source accessible** — project_path exists
3. **Language recognized** — valid programming language identifier
4. **Scope type valid** — matches `full-library`, `specific-modules`, `public-api`, or `component-library`
5. **Include patterns** — at least one glob pattern present
6. **Forge tier match** — matches forge_tier from config

**If validation fails for any brief:**
- Document the failure with specific field and reason
- Present to user for correction before writing
- Do NOT write invalid briefs

### 4. Present Generation Preview

"**Skill Brief Generation Preview**

**Units to generate:** {count}

{For each unit:}
---
**{unit-name}** → `{forge_data_folder}/{unit-name}/skill-brief.yaml`
```yaml
{complete YAML content}
```
---

**Validation:** {all passed / N issues found}
{List any validation issues}

**Ready to write {count} skill-brief.yaml files.** Confirm to proceed? (Y to write / N to abort / M to modify a specific brief)"

Wait for explicit user confirmation before writing files.

### 5. Write Files

**IF user confirms (Y):**

For each confirmed brief:
1. Create directory `{forge_data_folder}/{unit-name}/` if it does not exist
2. Write `skill-brief.yaml` to `{forge_data_folder}/{unit-name}/skill-brief.yaml`
3. Verify file was written successfully

**IF user modifies (M):**
- Ask which brief and what to change
- Update the YAML, re-validate, present again
- Return to confirmation prompt

**IF user aborts (N):**
- Document abort decision
- Skip file writing, proceed to report update

### 6. Determine Next Workflow Per Unit

For each generated brief, recommend the appropriate next workflow:

| Condition | Recommendation |
|-----------|---------------|
| Brief has `scope.type: full-library` and unit is well-bounded | create-skill — brief is sufficient for direct skill creation |
| Brief has `scope.type: component-library` and registry defines boundaries | create-skill — component boundaries defined by registry |
| Brief has `scope.type: specific-modules` or scope needs refinement | brief-skill — refine scope before creating skill |
| Brief has `scope.type: public-api` or complex interface | brief-skill — detailed scoping needed |
| Unit flagged as stack skill candidate | create-stack-skill — after individual skills exist |
| Unit flagged as already-skilled | update-skill — refresh existing skill |

### 7. Append to Report

Append the complete "## Generation Results" section to {outputFile}:

Replace `[Appended by step-06-generate-briefs]` with:

**Generated Briefs:**
| # | Unit Name | Output Path | Validation | Next Workflow |
|---|-----------|-------------|------------|---------------|
| {n} | {name} | {path} | {pass/fail} | {recommendation} |

**Generation Summary:**
- Total confirmed units: {count}
- Briefs generated: {count}
- Briefs skipped/failed: {count}
- Stack skill candidates flagged: {count}

**Next Steps:**
{For each next workflow recommendation, a clear action item}

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'step-06-generate-briefs' to existing array]
lastStep: 'step-06-generate-briefs'
nextWorkflow: '{primary recommendation}'
```

### 8. Present Completion Summary

"**Analyze-Source Workflow Complete**

**Project:** {project_name}
**Forge Tier:** {forge_tier}

**Results:**
- **Scanned:** {boundary count} boundaries detected
- **Identified:** {unit count} qualifying units classified
- **Confirmed:** {confirmed count} units approved for brief generation
- **Generated:** {brief count} skill-brief.yaml files written

**Files Created:**
{List each skill-brief.yaml with full path}

**Analysis Report:** {outputFile}

**Recommended Next Steps:**
{For each unit, the recommended next workflow with brief explanation}

{If stack skill candidates exist:}
**Stack Skill Candidates:**
{List candidates with recommendation to run create-stack-skill after individual skills are created}

**This analysis is complete.** To refine any brief, run the recommended next workflow. To re-analyze with different scope, run analyze-source again."

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every confirmed unit has a skill-brief.yaml generated and validated
- All required schema fields present and all 8 validation rules passed in each brief
- Files written to correct paths in forge_data_folder
- User confirmed before files were written
- Next workflow recommended per unit
- Generation Results section appended to report
- stepsCompleted fully populated and workflow marked complete
- Completion summary presented with clear next steps

### ❌ SYSTEM FAILURE:

- Generating briefs for units NOT in confirmed_units
- Writing files without user confirmation
- Missing required schema fields in generated YAML
- Not validating briefs against schema before writing
- Re-analyzing source code instead of using report data
- Not recommending next workflow per unit
- Not marking workflow as complete in frontmatter

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

---
name: 'step-09-report'
description: 'Display final stack skill summary with confidence distribution and next workflow recommendations'
---

# Step 9: Stack Skill Report

## STEP GOAL:

Display the final summary of the forged stack skill with confidence distribution, output file listing, and next workflow recommendations.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are Ferris delivering the final forge report
- ✅ Positive capability framing — lead with what was accomplished
- ✅ Warnings are secondary — present them only if they exist

### Step-Specific Rules:

- 🎯 This is the FINAL step — no nextStepFile
- 🚫 FORBIDDEN to write or modify any files — report is console output only
- 💬 Lead with the positive summary, then details, then warnings if any
- 🎯 Recommend next workflows based on what was produced

## EXECUTION PROTOCOLS:

- 🎯 Compile summary from all previous step results
- 📖 Display report to user — workflow is complete after this
- 🚫 No file writes, no state updates — this is terminal output

## CONTEXT BOUNDARIES:

- From step 01: project_name, forge_tier
- From step 03: confirmed_dependencies[] count
- From step 04: per_library_extractions[] with confidence tiers
- From step 05: integration_graph with pair count
- From step 07: written_files[] with paths
- From step 08: validation_result with findings
- This step produces: console report (no stored artifacts)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Display Stack Forged Banner

"**Stack forged: {project_name}-stack — {lib_count} libraries, {integration_count} integration patterns**

Forge tier: **{tier}**"

### 2. Display Confidence Distribution

"**Confidence distribution:**

| Tier | Count | Description |
|------|-------|-------------|
| T1 | {count} | AST-verified structural extraction |
| T1-low | {count} | Source reading inference |
| T2 | {count} | QMD-enriched temporal context |

{IF compose_mode:}
*Note: Confidence tiers above are inherited from source skills — they reflect the extraction method used when those skills were originally generated, not the current compose run.*
{END IF}"

### 3. Display Output File Summary

"**Output files:**

**Deliverables** (`{skills_output_folder}/{project_name}-stack/`):
- SKILL.md — Integration patterns, library summaries, conventions
- context-snippet.md — Compressed stack index ({token_estimate} tokens)
- metadata.json — Skill metadata and library registry
- references/ — {lib_count} per-library reference files
{If integrations:} - references/integrations/ — {pair_count} integration pair files

**Workspace** (`{forge_data_folder}/{project_name}-stack/`):
- provenance-map.json — Extraction source tracking
- evidence-report.md — Evidence and confidence breakdown"

### 4. Display Validation Summary

**If validation passed with no findings:**

"**Validation:** All checks passed"

**If validation had findings:**

"**Validation:** {warning_count} warning(s) found
{For each finding:}
- ⚠ {description}"

### 5. Display Warnings (Conditional)

**Only display if warnings exist from any step:**

"**Warnings:**
{For each warning from steps 04, 05, 07, 08:}
- {warning_description}"

**If no warnings:** Skip this section entirely.

### 6. Recommend Next Workflows

"**Next steps:**
- **[TS] test-skill** — Validate the stack skill against its own assertions
- **[EX] export-skill** — Package for distribution or agent loading

- **[VS] verify-stack** — Validate the stack's integration feasibility against your architecture document{IF compose_mode:} (re-run to confirm feasibility after any architecture changes from **[RA] refine-architecture**){END IF}

**Workflow complete.**"

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Banner displayed with accurate library and integration counts
- Confidence distribution table with correct tier counts
- All output files listed with descriptions
- Validation summary reflects actual step 08 findings
- Warnings displayed only when they exist
- Next workflow recommendations included
- Positive capability framing throughout

### ❌ SYSTEM FAILURE:

- Inaccurate counts in banner or distribution table
- Missing output files from the listing
- Displaying warnings section when no warnings exist
- Writing or modifying files in this step
- Not recommending next workflows
- Negative framing or apologetic tone

**Master Rule:** Celebrate what was built. Report accurately. Recommend next steps. Workflow complete.

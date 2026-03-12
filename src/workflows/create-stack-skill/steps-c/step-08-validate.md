---
name: 'step-08-validate'
description: 'Validate all output files against structure requirements and confidence tier completeness'

nextStepFile: './step-09-report.md'
stackSkillTemplate: '../data/stack-skill-template.md'
---

# Step 8: Validate Output

## STEP GOAL:

Validate all written output files against their expected structure and verify confidence tier label completeness.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a quality gate operator in Ferris Architect mode
- ✅ Validation is advisory — findings are warnings, not blockers
- ✅ Report findings accurately — do not downplay or exaggerate

### Step-Specific Rules:

- 🎯 Validate structure and completeness, not content quality
- 🚫 FORBIDDEN to modify any output files — validation is read-only
- 💬 Report findings with specific file paths and issue descriptions
- 🎯 Advisory mode: always proceed to report regardless of findings

## EXECUTION PROTOCOLS:

- 🎯 Check each deliverable file against its expected structure
- 💾 Store validation_result as workflow state
- 📖 Auto-proceed to report after validation complete
- 🚫 FORBIDDEN to halt on validation warnings (advisory only)

## CONTEXT BOUNDARIES:

- From step 07: written_files[] (all output artifacts with paths)
- From step 01: forge_tier, project_name, skills_output_folder, forge_data_folder
- This step produces: validation_result {status, findings[], warnings[]}
- This is a quality gate — findings inform the report but do not block it

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Verify File Existence

Check that all expected files exist from written_files[]:

**Deliverables** (`{skills_output_folder}/{project_name}-stack/`):
- [ ] SKILL.md
- [ ] context-snippet.md
- [ ] metadata.json
- [ ] references/ directory with per-library files
- [ ] references/integrations/ directory with pair files (if integrations detected)

**Workspace** (`{forge_data_folder}/{project_name}-stack/`):
- [ ] provenance-map.json
- [ ] evidence-report.md

Record any missing files as **ERROR** findings.

### 2. Validate SKILL.md Frontmatter (agentskills.io Compliance)

Verify SKILL.md has valid YAML frontmatter — REQUIRED for ecosystem compatibility:

- [ ] Frontmatter present — file starts with `---` delimiter and has closing `---`
- [ ] `name` field — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] `name` matches skill output directory name (`{project_name}-stack`)
- [ ] `description` field — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted

Record frontmatter violations as **WARNING** findings. Skills without valid frontmatter will fail `npx skills add` and `skills-ref validate`.

### 3. Validate SKILL.md Body Structure

Load `{stackSkillTemplate}` and verify SKILL.md contains expected sections:

- [ ] Header with project name, library count, integration count, forge tier
- [ ] Integration Patterns section (should appear BEFORE per-library summaries)
- [ ] Library Reference Index table
- [ ] Per-Library Summaries section
- [ ] Conventions section

Record missing sections as **WARNING** findings.

### 4. Validate metadata.json Fields

Parse metadata.json and verify required fields:

- [ ] `skill_type` equals "stack"
- [ ] `skill_name` matches `{project_name}-stack`
- [ ] `version` is present
- [ ] `created` is present
- [ ] `forge_tier` matches the tier from step 01
- [ ] `library_count` matches actual number of reference files
- [ ] `integration_count` matches actual integration pair files
- [ ] `libraries` array is present and non-empty
- [ ] `confidence_distribution` object is present with T1/T1-low/T2 keys

Record mismatches as **WARNING** findings.

### 5. Validate Reference File Completeness

For each confirmed library, verify `references/{library}.md` exists and contains:
- [ ] Library name header
- [ ] Version from manifest
- [ ] Key Exports section
- [ ] Usage Patterns section

For each integration pair (if any), verify `references/integrations/{libraryA}-{libraryB}.md` exists and contains:
- [ ] Integration pair header
- [ ] Type classification
- [ ] Integration Pattern section
- [ ] Key Files section

Record missing or incomplete files as **WARNING** findings.

### 6. Validate Confidence Tier Labels

Scan across all output files for confidence tier coverage:

- [ ] SKILL.md: Each per-library summary has a confidence label
- [ ] SKILL.md: Each integration pair entry has a confidence label
- [ ] Reference files: Each has a confidence label in its header
- [ ] metadata.json: confidence_distribution sums match library_count

Record missing tier labels as **WARNING** findings.

### 7. Validate context-snippet.md

Verify context-snippet.md follows ADR-L two-line format:
- [ ] Each library has an entry with import count and top exports
- [ ] Integration partners listed on second line
- [ ] No library from confirmed list is missing

Record format violations as **WARNING** findings.

### 8. Display Validation Results

**If all checks pass:**

"**Validation complete — all checks passed.**

- **Files:** {file_count}/{file_count} present
- **SKILL.md:** Structure valid
- **metadata.json:** All required fields present
- **References:** {lib_count} library + {pair_count} integration files verified
- **Confidence tiers:** Complete coverage

**Proceeding to summary report...**"

**If warnings found:**

"**Validation complete with {warning_count} finding(s).**

**Findings:**
{For each finding:}
- ⚠ {severity}: {description} — {file_path}

**Summary:**
- **Files:** {present_count}/{expected_count} present
- **Warnings:** {warning_count}
- **Errors:** {error_count}

{If errors (missing files):}
**Note:** Missing files may indicate a write failure in step 07. Review evidence-report.md for details.

**Proceeding to summary report...**"

### 9. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All expected files checked for existence
- SKILL.md validated against template structure
- metadata.json fields verified
- Reference files checked for completeness
- Confidence tier coverage verified
- Validation results displayed with specific findings
- Advisory mode: always proceeded to report

### ❌ SYSTEM FAILURE:

- Modifying any output files during validation
- Halting the workflow on validation warnings
- Not checking all expected files
- Reporting vague findings without file paths
- Skipping the confidence tier check

**Master Rule:** Validate everything, modify nothing. Advisory findings — always proceed to report.

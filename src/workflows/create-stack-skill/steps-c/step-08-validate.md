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

### 2. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds: Use skill-check for automated validation in sections 3, 9
- If fails: Use manual fallback paths in those sections

**Important:** Do not assume availability — empirical check required.

### 3. Validate SKILL.md via skill-check (if available)

**If available**, run: `npx skill-check check <skill-dir> --fix --format json --no-security-scan`

This validates frontmatter, description, body limits, links, formatting — and auto-fixes deterministic issues. Parse JSON for `qualityScore`, `diagnostics[]`, `fixed[]`.

**If `body.max_lines` reported**, prefer selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 content inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). Fall back to `npx skill-check split-body <skill-dir> --write` if not feasible. Verify `#quick-start` and `#key-types` anchors still resolve after split. Then re-validate.

**If unavailable**, perform manual frontmatter check:
- [ ] Frontmatter present with `---` delimiters
- [ ] `name` — present, non-empty, lowercase alphanumeric + hyphens, 1-64 chars, matches `{project_name}-stack`
- [ ] `description` — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` permitted

Record frontmatter violations as **WARNING** findings. Invalid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 4. Validate SKILL.md Body Structure

Load `{stackSkillTemplate}` and verify SKILL.md contains expected sections:

- [ ] Header with project name, library count, integration count, forge tier
- [ ] Integration Patterns section (before per-library summaries)
- [ ] Library Reference Index table
- [ ] Per-Library Summaries section
- [ ] Conventions section

Record missing sections as **WARNING** findings.

### 5. Validate metadata.json Fields

Parse metadata.json and verify required fields:

- [ ] `skill_type` equals "stack"
- [ ] `name` matches `{project_name}-stack`
- [ ] `version` and `generation_date` present
- [ ] `confidence_tier` matches forge tier from step 01 (Quick/Forge/Forge+/Deep) — in both code-mode and compose-mode, this is the forge tier; per-library inherited confidence is tracked separately in `confidence_distribution`
- [ ] `library_count` matches actual reference files; `integration_count` matches pair files
- [ ] `libraries` array present and non-empty
- [ ] `confidence_distribution` object present with `t1`, `t1_low`, `t2`, `t3` keys (lowercase, matching template definition)

Record mismatches as **WARNING** findings.

### 6. Validate Reference File Completeness

For each confirmed library, verify `references/{library}.md` contains: library name header, version from manifest (**in compose-mode**: version from source skill metadata), Key Exports section, Usage Patterns section.

For each integration pair, verify `references/integrations/{libraryA}-{libraryB}.md` contains: integration pair header, type classification, Integration Pattern section, Key Files section.

Record missing or incomplete files as **WARNING** findings.

### 7. Validate Confidence Tier Labels

Scan all output files for confidence tier coverage:

- [ ] SKILL.md: each per-library summary and integration pair entry has a confidence label
- [ ] Reference files: each has a confidence label in its header
- [ ] metadata.json: confidence_distribution sums match library_count

Record missing tier labels as **WARNING** findings.

### 8. Validate context-snippet.md

Verify context-snippet.md follows Vercel-aligned indexed format:
- [ ] First line matches: `[{project}-stack v{version}]|root: skills/{project}-stack/`
- [ ] Second line starts with `|IMPORTANT:`
- [ ] Stack and integrations lines present
- [ ] Approximate token count is ~80-120 tokens

Record format violations as **WARNING** findings.

### 9. Security Scan (if skill-check available)

Run: `npx skill-check check <skill-dir> --format json` (security scan enabled by default).

Record security findings as advisory **WARNING** findings — they do not block the report.

**If unavailable:** Skip with note in validation results.

### 10. Display Validation Results

**If all checks pass:**

"**Validation complete — all checks passed.** Files: {count}/{count} present. SKILL.md structure valid. metadata.json fields verified. {lib_count} library + {pair_count} integration files verified. Confidence tiers: complete coverage. **Proceeding to summary report...**"

**If warnings found:**

"**Validation complete with {warning_count} finding(s).** Findings: {list each: severity, description, file_path}. Files: {present}/{expected} present. Warnings: {count}. Errors: {count}. {If errors: Note missing files may indicate a write failure in step 07.} **Proceeding to summary report...**"

### 11. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All expected files checked; `npx skill-check check --fix` executed if available (or manual fallback)
- Quality score captured; auto-fix and split-body applied as needed; security scan executed (or skipped with note)
- SKILL.md validated against template; metadata.json fields verified; reference files checked
- Confidence tier coverage verified; validation results displayed with specific findings
- Advisory mode: always proceeded to report

### ❌ SYSTEM FAILURE:

- Modifying output files during validation (except via skill-check --fix)
- Halting on validation warnings; not checking all expected files
- Reporting vague findings without file paths; skipping confidence tier check
- Not recording quality score when skill-check is available

**Master Rule:** Validate everything, fix what's deterministic via skill-check, scan for security issues. Advisory findings — always proceed to report.

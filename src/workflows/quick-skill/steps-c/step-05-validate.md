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

### 1. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds (returns usage information): Continue to automated validation (section 2)
- If fails (command not found or error): Skip to manual fallback in section 2

**Important:** Use the verification command. Do not assume availability — empirical check required.

### 2. Validate SKILL.md via skill-check (if available)

**If `npx skill-check` is available**, run automated validation with auto-fix:

```bash
npx skill-check check <skill-dir> --fix --format json --no-security-scan
```

This validates frontmatter, description, body limits, links, and formatting — and auto-fixes deterministic issues (field ordering, slug format, required fields, trailing newlines).

**Parse JSON output** to extract:
- `qualityScore` — overall score (0-100)
- `diagnostics[]` — remaining issues after auto-fix
- `fixed[]` — issues automatically corrected

Record quality score and any remaining diagnostics as validation issues.

**If skill-check is NOT available**, perform manual frontmatter check:

- [ ] **Frontmatter present** — file starts with `---` delimiter and has closing `---`
- [ ] **`name` field** — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] **`name` matches directory** — frontmatter `name` matches the skill output directory name
- [ ] **`description` field** — present, non-empty, 1-1024 characters
- [ ] **No unknown fields** — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted

**For each violation, log an issue.** Missing frontmatter or missing required fields are high-severity issues — skills without valid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 3. Validate SKILL.md Body Structure

Check that SKILL.md has these required sections populated:

- [ ] **Overview section** present with package name, repo, language, authority
- [ ] **Description section** present with non-empty content
- [ ] **Key Exports section** present (may be empty if confidence is low)
- [ ] **Usage Patterns section** present (may have README fallback)

**For each missing or empty required section, log an issue.**

### 4. Validate Context Snippet Format

Check context-snippet.md format compliance:

- [ ] **Vercel-aligned indexed format** — pipe-delimited with version, retrieval instruction, section anchors
- [ ] **First line** matches pattern: `[{name} v{version}]|root: skills/{name}/`
- [ ] **Second line** starts with: `|IMPORTANT:`
- [ ] **Approximate token count** is ~80-120 tokens

**If format is wrong, log an issue.**

### 5. Validate Metadata JSON

Check metadata.json has required fields:

- [ ] `name` — present, non-empty
- [ ] `version` — present (auto-detected or "0.1.0")
- [ ] `source_authority` — must be "community"
- [ ] `source_repo` — present, valid GitHub URL
- [ ] `language` — present, non-empty
- [ ] `generated_by` — must be "quick-skill"
- [ ] `generation_date` — present
- [ ] `stats.exports_documented` — present, number
- [ ] `stats.exports_public_api` — present, number
- [ ] `stats.exports_total` — present, number
- [ ] `stats.public_api_coverage` — present, number
- [ ] `stats.total_coverage` — present, number
- [ ] `confidence_tier` — present

**For each missing or invalid field, log an issue.**

### 6. Security Scan (if skill-check available)

Run security scan on the compiled skill:

```bash
npx skill-check check <skill-dir> --format json
```

(Security scan is enabled by default when `--no-security-scan` is omitted.)

Record any security findings as advisory warnings. Security issues do not block output.

**If skill-check unavailable:** Skip with note in validation results.

### 7. Report Validation Results

"**Validation complete:**

**SKILL.md:** {pass/issues found} (quality score: {score}/100 if skill-check was available)
{list any issues}
{list any auto-fixed issues}

**context-snippet.md:** {pass/issues found}
{list any issues}

**metadata.json:** {pass/issues found}
{list any issues}

**Security:** {pass/warn/skipped}
{list any security findings}

**Overall:** {pass / N issues found}

{If issues found:}
These issues are advisory for community-tier skills. You can proceed to write output or go back to adjust.

**Proceeding to write output...**"

Set `validation_result` with pass/fail status, quality score, and issues list.

### 8. Auto-Proceed to Write

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

- `npx skill-check check --fix --format json` executed if available (or manual fallback)
- Quality score (0-100) captured when skill-check available
- Auto-fix applied via `--fix` for deterministic issues
- Security scan executed (or skipped with note)
- All three outputs validated against requirements
- Issues reported clearly with specific details
- Community-tier validation applied (not official-tier strictness)
- validation_result set with pass/fail, quality score, and issues list
- Auto-proceeding to write step

### ❌ SYSTEM FAILURE:

- Modifying compiled content instead of just reporting
- Blocking output on validation issues (advisory only)
- Skipping validation checks
- Not reporting found issues
- Not recording quality score when skill-check is available

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

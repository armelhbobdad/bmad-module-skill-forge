---
name: 'step-06-validate'
description: 'Validate compiled skill content against agentskills.io spec via skills_ref'
nextStepFile: './step-07-generate-artifacts.md'
---

# Step 6: Validate

## STEP GOAL:

To validate the compiled SKILL.md content against the agentskills.io specification using skills_ref, auto-fix any validation failures, and confirm spec compliance before artifact generation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing quality assurance
- ✅ Validation ensures spec compliance — it does not modify content semantics
- ✅ Tool unavailability means skip validation, not halt workflow

### Step-Specific Rules:

- 🎯 Focus ONLY on validating compiled content against spec
- 🚫 FORBIDDEN to add new content — only fix spec compliance issues
- 🚫 FORBIDDEN to write files — content stays in context until step-07
- 💬 If auto-fix fails, report issues clearly but proceed (warn, don't halt)
- ⚙️ If skills_ref unavailable: skip validation, add warning to evidence report

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Validation results are added to evidence-report content in context
- 📖 Auto-fix pattern: validate → fix → re-validate (once)
- 🚫 Maximum one auto-fix attempt per validation failure

## CONTEXT BOUNDARIES:

- Available: All compiled content from step-05 (SKILL.md, metadata.json, etc.)
- Focus: Spec compliance validation and auto-fix
- Limits: Do NOT add new content or modify extraction data
- Dependencies: Compiled content must exist from step-05

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tool Availability

**If skills_ref tool is available:**
Continue to validation steps.

**If skills_ref tool is NOT available:**
- Perform manual frontmatter compliance check (see step 3 fallback below)
- Add note to evidence-report content: "Spec validation performed manually — skills_ref tool unavailable"

### 2. Validate Schema

Use `skills_ref.validate_schema()` against the compiled SKILL.md content.

**Check:**
- Required sections present (Overview, Quick Start, API Reference, Type Definitions)
- Section order follows agentskills.io standard
- Frontmatter contains required fields (name, description) with no disallowed fields
- Provenance citations present in API Reference entries

**If validation passes:** Record "Schema: PASS" in evidence-report content.

**If validation fails:**
1. Identify specific failures
2. Attempt auto-fix (structural adjustments only — never invent content)
3. Re-validate once
4. If still failing: record "Schema: FAIL — {specific issues}" in evidence-report, add warnings, but proceed

### 3. Validate Frontmatter

**If skills_ref available:** Use `skills_ref.validate_frontmatter()` against the SKILL.md frontmatter.

**If skills_ref NOT available (fallback):** Perform manual frontmatter compliance check.

**Check (agentskills.io specification):**

- [ ] Frontmatter present — file starts with `---` and has closing `---`
- [ ] `name` field — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] `name` matches skill output directory name
- [ ] `description` field — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted
- [ ] `version` and `author` are NOT in frontmatter (they belong in metadata.json)

**If validation passes:** Record "Frontmatter: PASS" in evidence-report content.

**If validation fails:**
1. Auto-fix frontmatter (these are deterministic fixes — remove disallowed fields, add missing required fields)
2. Re-validate once
3. Record result in evidence-report

### 4. Validate metadata.json

Cross-check metadata.json content against extraction inventory:
- `stats.exports_documented` matches actual documented exports
- `stats.exports_total` matches total extracted exports
- `stats.coverage` is accurate (documented / total)
- `confidence_t1`, `confidence_t2`, `confidence_t3` match actual counts
- `spec_version` is "1.3"

Auto-fix any discrepancies (these are computed values).

### 5. Update Evidence Report

Add validation results to the evidence-report content in context:

```markdown
## Validation Results
- Schema: {pass/fail}
- Frontmatter: {pass/fail}
- Metadata: {pass/fail}

## Warnings
- {any warnings from validation}
```

### 6. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After validation is complete (or skipped if tools unavailable), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed validation step with no user choices
- Tool unavailability is a skip, not a halt
- Validation failures are warnings — proceed to artifact generation
- Proceed directly to next step after validation completes

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN validation is complete (or skipped) and evidence-report content is updated will you proceed to load `{nextStepFile}` for artifact generation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Schema validation attempted (or skipped with warning if tool unavailable)
- Frontmatter validation attempted
- Metadata cross-check performed
- Auto-fix applied for deterministic failures
- Evidence report updated with validation results
- Warnings recorded for any failures
- Auto-proceeded to step-07

### ❌ SYSTEM FAILURE:

- Halting the workflow on validation failure (should warn and proceed)
- Halting on skills_ref unavailability (should skip with warning)
- Adding new content during validation (only structural fixes allowed)
- Not recording validation results in evidence report
- Attempting more than one auto-fix cycle per failure

**Master Rule:** Validation informs, it does not block. Record results, fix what's deterministic, warn about the rest, and proceed.

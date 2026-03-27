---
name: 'step-04-requirements'
description: 'Pass 3 (OPTIONAL) — if PRD/vision document provided, verify the stack covers stated requirements'

nextStepFile: './step-05-synthesize.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 4: Requirements Coverage

## STEP GOAL:

If a PRD or vision document was provided in Step 01, verify that the combined capabilities of the generated skills address each stated requirement. If no PRD was provided, skip this pass and auto-proceed. Produce a requirements coverage table with Fulfilled, Partially Fulfilled, or Not Addressed verdicts.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a stack verification analyst assessing requirements coverage
- ✅ Every verdict must reason from actual skill capabilities, not assumptions
- ✅ "Not Addressed" is a valid and important finding — do not force-fit skills to requirements

### Step-Specific Rules:

- 🎯 Focus ONLY on requirements-to-skills coverage assessment
- 🚫 FORBIDDEN to re-analyze integrations — that was Step 03
- 🚫 FORBIDDEN to synthesize or produce overall verdicts — that is Step 05
- 💬 If no PRD was provided, skip immediately with a clear message

## EXECUTION PROTOCOLS:

- 🎯 Extract requirements from PRD/vision document and assess skill coverage
- 💾 Append Requirements Coverage section to {outputFile}
- 📖 Auto-proceed to next step after completion or skip
- 🚫 Only requirements coverage — no synthesis, no overall verdict

## CONTEXT BOUNDARIES:

- Available: PRD/vision document (if provided), skill SKILL.md files, metadata.json files
- Focus: Mapping requirements to skill capabilities
- Limits: Do not evaluate skill quality — only whether capabilities match requirements
- Dependencies: Step 01 (PRD availability flag, skill inventory)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check PRD Availability

**Check `prd_available` from workflow state (set in Step 01). If `prd_available` is false (no PRD/vision document was provided):**

"**Pass 3: Requirements Coverage — Skipped**

No PRD or vision document was provided. Requirements coverage analysis requires a document describing project capabilities and constraints.

To include this pass, re-run **[VS]** with a PRD or vision document path.

**Proceeding to synthesis...**"

Update {outputFile} frontmatter: append `'step-04-requirements'` to `stepsCompleted`, set `requirements_pass: "skipped"`.

Load, read the full file and then execute `{nextStepFile}`. **STOP HERE — do not execute sections 2-6.**

**If PRD/vision document was provided:** Continue to section 2.

### 2. Extract Requirements

Parse the PRD/vision document for capability requirements.

**Look for:**
- **Feature descriptions** — explicit capabilities the product must have
- **Technical requirements** — performance targets, scalability needs, platform support
- **Non-functional requirements** — offline-first, real-time sync, multi-language support, accessibility, security constraints
- **Integration requirements** — third-party service dependencies, API contracts
- **Infrastructure requirements** — deployment targets, CI/CD needs, monitoring

**Build a requirements list** with each entry containing:
- `requirement_id` — sequential identifier (R1, R2, R3...)
- `requirement_text` — the stated requirement
- `category` — feature, technical, non-functional, integration, or infrastructure
- `source_section` — the PRD section where it was found

### 3. Assess Stack Coverage

For each requirement, evaluate whether the combined capabilities of the generated skills address it.

**Assessment method:**
- Read each skill's SKILL.md exports, description, and capabilities sections
- Check if skill exports provide functions, types, or patterns relevant to the requirement
- Consider combinations of multiple skills that together address a requirement
- For non-functional requirements, check if skills document relevant configuration or patterns

**Assign verdict per requirement:**
- **Fulfilled** — one or more skills clearly provide the needed capability, with specific exports or patterns identified
- **Partially Fulfilled** — skills provide related capability but gaps remain (specify what is covered and what is not)
- **Not Addressed** — no skill in the stack provides capability relevant to this requirement

**Each verdict MUST include:**
- Which skills contribute (if any)
- Specific exports or capabilities from those skills that are relevant
- For Partially Fulfilled: what gap remains

### 4. Display Requirements Results

"**Pass 3: Requirements Coverage**

| ID | Requirement | Category | Verdict | Contributing Skills |
|----|-------------|----------|---------|-------------------|
| {id} | {requirement_text} | {category} | {Fulfilled/Partially Fulfilled/Not Addressed} | {skill_names or '—'} |

**Coverage: {fulfilled_count} Fulfilled, {partial_count} Partially Fulfilled, {not_addressed_count} Not Addressed**

{IF any Not Addressed:}
**Unaddressed Requirements — Recommendations:**
{For each not addressed requirement:}
- **{id}:** {requirement_text} → Evaluate `{category}` libraries that provide this capability, generate a skill with **[CS]** or **[QS]**, then re-run **[VS]**

{IF any Partially Fulfilled:}
**Partial Coverage — Details:**
{For each partially fulfilled requirement:}
- **{id}:** Covered by `{skill_names}` — **Gap:** {what remains unaddressed}"

### 5. Append to Report

Write the **Requirements Coverage** section to `{outputFile}`:
- Include the full requirements coverage table
- Include recommendations for Not Addressed and Partially Fulfilled items
- Update frontmatter: append `'step-04-requirements'` to `stepsCompleted`
- Set `requirements_pass: "completed"`
- Set `requirements_fulfilled`, `requirements_partial`, `requirements_not_addressed` counts

### 6. Auto-Proceed to Next Step

"**Proceeding to synthesis...**"

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- PRD availability checked first — skipped cleanly if not provided
- All requirements extracted from PRD with source section citations
- Each requirement assessed against actual skill capabilities (exports, descriptions)
- Verdicts include contributing skill names and specific capabilities
- Not Addressed items have actionable recommendations
- Requirements Coverage section appended to {outputFile}
- Auto-proceeded to step 05

### ❌ SYSTEM FAILURE:

- Fabricating requirements not stated in the PRD document
- Force-fitting skills to requirements they do not address
- Verdicts without evidence from actual skill content
- Not executing the skip path when no PRD was provided
- Producing synthesis or overall verdicts (that is Step 05)
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

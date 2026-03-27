---
name: 'step-02-detect-mode'
description: 'Determine naive (individual) vs contextual (stack) testing mode'

nextStepFile: './step-03-coverage-check.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
---

# Step 2: Detect Mode

## STEP GOAL:

Examine the skill metadata to determine whether this is an individual skill (naive mode — API surface coverage only) or a stack skill (contextual mode — full coherence validation including cross-references and integration patterns).

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER override mode detection with assumptions — use actual metadata
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor in Ferris's Audit mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Mode detection is deterministic — based on metadata, not judgment
- ✅ Report the detected mode clearly and explain what it means for analysis depth

### Step-Specific Rules:

- 🎯 Focus only on mode detection — do NOT begin coverage or coherence analysis
- 🚫 FORBIDDEN to start analyzing exports or references in this step
- 💬 Explain what each mode means for the upcoming analysis
- 📋 Set testMode in output frontmatter before proceeding

## EXECUTION PROTOCOLS:

- 🎯 Read skill metadata to determine type
- 💾 Update {outputFile} frontmatter with testMode and append Test Summary section
- 📖 Update stepsCompleted in {outputFile}
- 🚫 FORBIDDEN to proceed without setting testMode

## CONTEXT BOUNDARIES:

- Available: Skill metadata loaded in step 01, forge tier state, output document
- Focus: Mode detection only — classify skill type, set test mode
- Limits: Do not analyze content — just determine the correct testing mode
- Dependencies: step-01 must have validated skill exists and loaded metadata

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Examine Skill Type

Read the skill metadata (loaded in step 01) and check:

**Individual Skill indicators:**
- `skill_type: 'single'` in metadata
- Single source library/package
- No cross-references to other skills
- Self-contained API surface

**Stack Skill indicators:**
- `skill_type: 'stack'` in metadata
- References multiple skills or packages
- Contains cross-references in SKILL.md
- Integration patterns documented between components

### 2. Determine Test Mode

**IF individual skill → Naive Mode:**
- Coverage check: documented exports vs source API surface
- Coherence check: basic structural validation only (no cross-references to verify)
- Scoring: redistributed weights (no coherence category)

**IF stack skill → Contextual Mode:**
- Coverage check: documented exports vs source API surface (same as naive)
- Coherence check: full validation — cross-references exist, types match, integration patterns complete
- Scoring: full category weights including coherence

**IF metadata unclear or skill_type not set:**
- Default to **naive mode** (conservative — fewer checks, less chance of false negatives from missing context)
- Note the default in the report

**Quick-tier adjustment (applies to both modes):** If `forge_tier` is `Quick`, Signature Accuracy and Type Coverage are skipped during scoring (no AST available). Their weights are redistributed proportionally to remaining active categories. See `scoring-rules.md` Tier-Dependent Scoring section for details.

### 3. Update Output Document

Update `{outputFile}` frontmatter:
- Set `testMode: '{naive|contextual}'`

Append the **Test Summary** section to `{outputFile}`:

```markdown
## Test Summary

**Skill:** {skill_name}
**Test Mode:** {naive|contextual}
**Forge Tier:** {detected_tier}

**Mode Rationale:** {brief explanation of why this mode was selected}

**Analysis Plan:**
- Coverage Check: {what will be checked based on mode + tier}
- Coherence Check: {what will be checked based on mode + tier}
```

### 4. Report Mode Detection

"**Mode detected: {NAIVE|CONTEXTUAL}**

**{skill_name}** is {an individual skill / a stack skill}, so we'll run in **{naive/contextual}** mode.

**What this means:**
- Coverage: {brief description of coverage scope}
- Coherence: {brief description of coherence scope}
- Scoring: {which weight distribution applies}

**Proceeding to coverage check...**"

### 5. Auto-Proceed

Display: "**Proceeding to coverage check...**"

#### Menu Handling Logic:

- After mode detection is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed detection step with no user choices
- Proceed directly to next step after mode is set

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN testMode is set in the output frontmatter and the Test Summary section is appended to the output document, will you then load and read fully `{nextStepFile}` to execute coverage check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill type correctly identified from metadata
- Test mode set (naive or contextual) in output frontmatter
- Test Summary section appended to output document
- Mode rationale documented
- Analysis plan stated based on mode + tier combination
- Auto-proceeded to step 03

### ❌ SYSTEM FAILURE:

- Guessing mode without reading metadata
- Not setting testMode in output frontmatter
- Not appending Test Summary section
- Starting analysis in this step
- Hardcoding paths instead of using frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

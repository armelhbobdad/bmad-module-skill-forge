---
nextStepFile: './step-03-coverage-check.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
---

# Step 2: Detect Mode

## STEP GOAL:

Examine the skill metadata to determine whether this is an individual skill (naive mode — API surface coverage only) or a stack skill (contextual mode — full coherence validation including cross-references and integration patterns).

## Rules

- Focus only on mode detection — do not begin coverage or coherence analysis
- Set testMode in output frontmatter before proceeding

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


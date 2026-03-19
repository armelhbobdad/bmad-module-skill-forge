---
name: 'step-04-coherence-check'
description: 'Validate internal consistency — references, types, and integration patterns'

nextStepFile: './step-04b-external-validators.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
outputFormatsFile: '../data/output-section-formats.md'
---

# Step 4: Coherence Check

## STEP GOAL:

Validate internal consistency of the skill documentation. In contextual mode (stack skills): verify that all cross-references in SKILL.md point to real files, types match their declarations, and integration patterns are complete. In naive mode (individual skills): perform basic structural validation only.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER fabricate references or claim files exist without verifying — zero hallucination
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor in Ferris's Audit mode — zero hallucination
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Every broken reference must cite exactly what was referenced and where it was expected
- ✅ Report structural facts — do not interpret or editorialize

### Step-Specific Rules:

- 🎯 Use subprocess optimization: grep for references across files, then per-reference deep validation
- 💬 Subprocess returns structured findings only, not full file contents
- 🚫 DO NOT BE LAZY — For EACH reference in contextual mode, launch a subprocess to validate the target
- ⚙️ If subprocess unavailable, perform validation in main thread sequentially
- 📋 Analysis depth is conditional on testMode (naive vs contextual)

## EXECUTION PROTOCOLS:

- 🎯 Check testMode from output frontmatter to determine analysis depth
- 💾 Append Coherence Analysis section to {outputFile}
- 📖 Update stepsCompleted in {outputFile}
- 🚫 FORBIDDEN to skip coherence check entirely — even naive mode runs basic structural validation

## CONTEXT BOUNDARIES:

- Available: SKILL.md, source files, testMode, forge tier, coverage results from step 03, evidence-report.md from skill's forge-data directory (Deep tier only)
- Focus: Internal consistency and reference validation only — coverage was step 03
- Limits: Do NOT recalculate coverage scores — use results from step 03
- Dependencies: step-03 must have completed coverage analysis

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Test Mode

Read `testMode` from `{outputFile}` frontmatter.

**IF naive mode → Execute Naive Coherence (Section 2)**
**IF contextual mode → Execute Contextual Coherence (Sections 3-5)**

### 2. Naive Mode: Basic Structural Validation

Perform lightweight structural checks:

**Document structure:**
- SKILL.md has required top-level sections (description, exports, usage)
- Section headers are properly formatted
- Code examples have language annotations
- No broken markdown (unclosed code blocks, malformed tables)

**Internal consistency:**
- Exports referenced in usage examples match exports listed in exports section
- Type names used in examples match documented types
- No self-contradictions (e.g., function described as async but shown sync in example)

Build a simple structural findings list:

```json
{
  "structural_issues": [
    {"type": "missing_section", "detail": "No 'Usage' section found"},
    {"type": "broken_example", "detail": "Line 42: references undeclared function 'getConfig'"}
  ],
  "issues_found": 2
}
```

**After naive coherence → Skip to Section 6 (Append Results)**

### 3. Contextual Mode: Extract References

Scan SKILL.md for all cross-references:

**Reference types to extract:**
- File path references (`./path/to/file.ts`, `../shared/types.ts`)
- Skill references (`See SKILL.md for {other-skill}`, `Integrates with {package}`)
- Type imports (`import { Type } from './module'`)
- Integration pattern references (middleware chains, plugin hooks, shared state)

Launch a subprocess to grep/regex SKILL.md for reference patterns and return all found references with line numbers as structured JSON (`references_found[]` with line, type, target fields). If subprocess unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

DO NOT BE LAZY — For EACH reference found, launch a subprocess that:

1. Checks if the target exists (file exists, skill exists, type is declared)
2. If target exists, validates the reference is accurate:
   - File path references: file exists at specified path
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
3. Returns structured validation JSON per reference (reference, line, target_exists, type_match, signature_match, issues[])

If subprocess unavailable, validate each reference in main thread.

### 5. Contextual Mode: Check Integration Pattern Completeness

For stack skills, verify integration patterns are complete:

- **All documented integration points have corresponding code examples**
- **Shared types are consistently used across referenced components**
- **Middleware/plugin chains show complete flow, not fragments**
- **Event handlers reference valid event types**

Build integration completeness findings:

```json
{
  "patterns_documented": 5,
  "patterns_complete": 4,
  "incomplete_patterns": [
    {
      "pattern": "Auth middleware chain",
      "issue": "Shows middleware registration but not the handler function signature",
      "line": 95
    }
  ]
}
```

### 5b. Contextual Mode + Deep Tier: Section 4b Verification

**Only execute if forge tier is Deep.** Skip silently for Quick/Forge tiers.

Check whether SKILL.md contains a "Migration & Deprecation Warnings" section (Section 4b). Then check the skill's `evidence-report.md` (at `forge-data/{skill_name}/evidence-report.md`) for T2-future annotation counts.

- **If T2-future annotations > 0 AND Section 4b is absent:** Flag as Medium severity gap: "Migration section missing — T2-future annotations exist but Section 4b is not present in SKILL.md Tier 1."
- **If T2-future annotations = 0 AND Section 4b is present:** Flag as Medium severity gap: "Migration section unexpected — Section 4b is present but no T2-future annotations were produced."
- **If evidence-report.md is unavailable:** Skip this check silently. Note: "Section 4b verification skipped — evidence-report.md not found."

Add findings to the coherence analysis results.

### 6. Append Coherence Analysis to Output

Load `{outputFormatsFile}` and use the appropriate Coherence Analysis section format (naive or contextual) to append findings to `{outputFile}`.

### 7. Report Coherence Results

**For Naive Mode:**
"**Coherence check complete (naive mode).**

Basic structural validation of **{skill_name}**:
- {N} structural issues found
- Coherence category not scored (weight redistributed to coverage)

**Proceeding to external validation...**"

**For Contextual Mode:**
"**Coherence check complete (contextual mode).**

Reference validation of **{skill_name}**:
- References: {valid}/{total} valid ({percentage}%)
- Integration patterns: {complete}/{total} complete ({percentage}%)
- Combined coherence: {percentage}%

**{N} issues found** — details in Coherence Analysis section.

**Proceeding to external validation...**"

### 8. Auto-Proceed

Display: "**Proceeding to external validation...**"

#### Menu Handling Logic:

- After coherence analysis is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed validation step with no user choices
- Proceed directly to next step after coherence is analyzed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN coherence analysis is complete (naive structural or contextual full validation), the Coherence Analysis section has been appended to {outputFile}, and coherence scores (if contextual) have been calculated, will you then load and read fully `{nextStepFile}` to execute external validation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Correct mode path executed (naive structural OR contextual full)
- All references validated in contextual mode (DO NOT BE LAZY)
- Every broken reference cites exact location and expected target
- Coherence Analysis section appended to output document
- Coherence scores calculated (contextual) or weight redistribution noted (naive)
- Zero fabricated findings — all traceable to artifacts

### ❌ SYSTEM FAILURE:

- Skipping coherence check entirely (even naive mode runs structural checks)
- Fabricating reference validation results
- Not checking every reference in contextual mode (DO NOT BE LAZY)
- Running contextual checks on a naive-mode skill (unnecessary depth)
- Running only naive checks on a contextual-mode skill (insufficient depth)
- Hardcoding paths instead of using frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. Zero hallucination — every finding traces to artifacts.

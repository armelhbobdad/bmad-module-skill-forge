---
nextStepFile: './step-04b-external-validators.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
---

# Step 4: Coherence Check

## STEP GOAL:

Validate internal consistency of the skill documentation. In contextual mode (stack skills): verify that all cross-references in SKILL.md point to real files, types match their declarations, and integration patterns are complete. In naive mode (individual skills): perform basic structural validation only.

## Rules

- Use subprocess optimization: grep for references, then per-reference deep validation
- For each reference in contextual mode, launch a subprocess to validate the target — do not shortcut
- Analysis depth is conditional on testMode (naive vs contextual)

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
- If `scripts/` or `assets/` directory exists alongside SKILL.md, a "Scripts & Assets" section (Section 7b) should be present

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

**After naive coherence → Execute Section 2b if gate conditions met, then skip to Section 6 (Append Results)**

### 2b. Migration/Deprecation Verification (Mode-Independent)

**Gate check:** Execute this section ONLY IF both conditions are met:
1. Forge tier is **Deep** (tool-gated)
2. `{forge_data_folder}/{skill_name}/evidence-report.md` exists (data-gated)

If either condition fails, skip silently and proceed to Section 6.

**This check runs regardless of naive/contextual mode.** T2-future annotations are a property of the source code and enrichment data, not the skill type.

Check whether SKILL.md contains a "Migration & Deprecation Warnings" section (Section 4b). Then check the skill's `evidence-report.md` (at `{forge_data_folder}/{skill_name}/evidence-report.md`) for T2-future annotation counts.

- **If T2-future annotations > 0 AND Section 4b is absent:** Flag as Medium severity gap: "Migration section missing — T2-future annotations exist but Section 4b is not present in SKILL.md Tier 1."
- **If T2-future annotations = 0 AND Section 4b is present:** Flag as Medium severity gap: "Migration section unexpected — Section 4b is present but no T2-future annotations were produced."
- **If evidence-report.md is unavailable:** Skip this check silently. Note: "Section 4b verification skipped — evidence-report.md not found."

Add findings to the coherence analysis results.

**After Section 2b (naive path) → Skip to Section 6 (Append Results)**

### 3. Contextual Mode: Extract References

Scan SKILL.md for all cross-references:

**Reference types to extract:**
- File path references (`./path/to/file.ts`, `../shared/types.ts`)
- Skill references (`See SKILL.md for {other-skill}`, `Integrates with {package}`)
- Type imports (`import { Type } from './module'`)
- Integration pattern references (middleware chains, plugin hooks, shared state)
- Script/asset references (`scripts/{file}`, `assets/{file}`) in SKILL.md body

Launch a subprocess to grep/regex SKILL.md for reference patterns and return all found references with line numbers as structured JSON (`references_found[]` with line, type, target fields). If subprocess unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

DO NOT BE LAZY — For EACH reference found, launch a subprocess that:

1. Checks if the target exists (file exists, skill exists, type is declared)
2. If target exists, validates the reference is accurate:
   - File path references: file exists at specified path
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
   - Script/asset references: verify the referenced file exists in the skill's `scripts/` or `assets/` directory
3. Returns structured validation JSON per reference (reference, line, target_exists, type_match, signature_match, issues[])

If subprocess unavailable, validate each reference in main thread.

4. **Scripts/assets directory check:** If a `scripts/` or `assets/` directory exists alongside SKILL.md, verify that a "Scripts & Assets" section (Section 7b) is present in SKILL.md. This directory-level check applies in both modes (naive mode performs it in Section 2; contextual mode performs it here alongside per-reference validation). Flag absence as Medium severity gap per `{scoringRulesFile}`.

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

**Zero integration patterns:** If no integration patterns are documented in SKILL.md (e.g., a contextual-mode skill that uses shared types but has no middleware chains, plugin hooks, or event flows): record `patterns_documented: 0`, `patterns_complete: 0`. The coherence score will use reference validity alone — see `{scoringRulesFile}` Coherence Score Aggregation: "If no integration patterns exist, combined coherence equals reference validity."

### 5b. Migration/Deprecation Verification (Contextual Path)

**This section shares logic with Section 2b.** If updating the shared logic, ensure both sections remain synchronized. If you are on the contextual mode path (Sections 3-5), execute the migration check here using the same rules as Section 2b:

**Gate check:** Execute ONLY IF both conditions are met:
1. Forge tier is **Deep** (tool-gated)
2. `{forge_data_folder}/{skill_name}/evidence-report.md` exists (data-gated)

If either condition fails, skip silently.

Check whether SKILL.md contains a "Migration & Deprecation Warnings" section (Section 4b). Then check the skill's `evidence-report.md` for T2-future annotation counts.

- **If T2-future annotations > 0 AND Section 4b is absent:** Flag as Medium severity gap: "Migration section missing — T2-future annotations exist but Section 4b is not present in SKILL.md Tier 1."
- **If T2-future annotations = 0 AND Section 4b is present:** Flag as Medium severity gap: "Migration section unexpected — Section 4b is present but no T2-future annotations were produced."
- **If evidence-report.md is unavailable:** Skip this check silently. Note: "Section 4b verification skipped — evidence-report.md not found."

Add findings to the coherence analysis results.

### 5c. Calculate Coherence Scores

**Contextual mode only.** Calculate coherence percentages using the formulas defined in `{scoringRulesFile}` — Coherence Score Aggregation section:

```
reference_validity = (valid_references / total_references) * 100
integration_completeness = (complete_patterns / total_patterns) * 100
combined_coherence = (reference_validity * 0.6) + (integration_completeness * 0.4)
```

**Edge case:** If no integration patterns are documented (patterns_documented = 0), combined coherence equals reference validity alone. Do not divide by zero.

These values fill the `{percentage}%` placeholders in the output template loaded in Section 6.

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


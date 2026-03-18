---
name: 'step-03-coverage-check'
description: 'Compare documented exports in SKILL.md against actual source API surface'

nextStepFile: './step-04-coherence-check.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
scoringRulesFile: '../data/scoring-rules.md'
---

# Step 3: Coverage Check

## STEP GOAL:

Compare the exports, functions, classes, types, and interfaces documented in SKILL.md against the actual source code API surface. Identify missing documentation, undocumented exports, and signature mismatches. Analysis depth scales with forge tier.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER fabricate findings — every coverage result must trace to actual source code or SKILL.md content
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor in Ferris's Audit mode — zero hallucination
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Every finding must include file:line citations from source code
- ✅ Report what IS documented vs what SHOULD BE documented — facts only

### Step-Specific Rules:

- 🎯 Use subprocess optimization for per-file AST analysis (Pattern 2) when available
- 💬 Subprocess returns structured findings only, not full file contents
- 🚫 DO NOT BE LAZY — For EACH source file, launch a subprocess for deep analysis
- ⚙️ If subprocess unavailable, perform analysis in main thread sequentially
- 📋 Coverage depth must match the detected forge tier

## EXECUTION PROTOCOLS:

- 🎯 Load SKILL.md exports section and source files
- 💾 Append Coverage Analysis section to {outputFile}
- 📖 Update stepsCompleted in {outputFile}
- 🚫 FORBIDDEN to proceed without completing all source file analysis

## CONTEXT BOUNDARIES:

- Available: SKILL.md, source files, forge tier, test mode from step 02
- Focus: Export coverage comparison only — coherence is step 04
- Limits: Do NOT validate cross-references or integration patterns (that's coherence)
- Dependencies: step-02 must have set testMode and reported forge tier

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 0. Check for Docs-Only Mode

**If metadata.json indicates `confidence_tier: "Quick"` and all SKILL.md citations are `[EXT:...]` format (docs-only skill):**

Coverage scoring adapts: instead of comparing SKILL.md against source code exports, compare SKILL.md documented items against themselves for internal completeness (every documented function has a description, parameters, and return type). Score based on documentation completeness rather than source coverage. Set `docs_only_mode: true` in context for step-05 scoring.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

**If source-based skill:** Continue with standard coverage check below.

### 0b. Define Source API Surface

**Source API surface** = the package's top-level public exports. These are the symbols reachable from the primary entry point without importing internal modules:

- **Python:** symbols exported in `__init__.py` (including re-exports) — exclude private (`_prefixed`) names
- **TypeScript/JavaScript:** named exports from `index.ts` / `index.js` — exclude unexported locals
- **Go:** exported identifiers (capitalized) from the package's public-facing files
- **Rust:** items in `pub use` from `lib.rs` or `mod.rs`

Internal module symbols are **excluded** from the coverage denominator unless they are explicitly documented in SKILL.md (in which case they count as documented extras, not missing coverage).

This matches the extraction-patterns.md convention used during skill creation: coverage measures how well SKILL.md documents what users actually import, not the entire internal codebase.

### 1. Extract Documented Exports from SKILL.md

Read SKILL.md and extract all documented items:

- **Functions:** name, parameters, return type, description
- **Classes:** name, methods, properties
- **Types/Interfaces:** name, fields
- **Constants/Enums:** name, values
- **Hooks/Patterns:** name, usage signature

Build the **documented inventory** — a list of everything the SKILL.md claims the source provides.

### 2. Analyze Source Code (Tier-Dependent)

Start from the package entry point (see 0b) and identify the public API surface. Then analyze those exports at the appropriate tier depth.

**Quick Tier (no tools):**
- Read the entry point file(s) directly
- Identify public exports by scanning for `export` keywords, `module.exports`, `__init__.py` imports, or language-specific export patterns
- Compare against documented inventory by name matching
- Cannot verify signatures — note as "unverified" in report

**Forge Tier (ast-grep available):**
DO NOT BE LAZY — For EACH source file that defines public API exports, launch a subprocess that:
1. Uses ast-grep to extract all exported symbols with their full signatures
2. Matches each export against the documented inventory
3. Returns structured findings:

```json
{
  "file": "src/utils.ts",
  "exports_found": ["formatDate", "parseConfig", "ConfigType"],
  "exports_documented": ["formatDate", "parseConfig"],
  "missing_docs": ["ConfigType"],
  "signature_mismatches": [
    {
      "name": "formatDate",
      "source_sig": "(date: Date, format?: string) => string",
      "documented_sig": "(date: Date) => string",
      "issue": "missing optional parameter 'format'"
    }
  ]
}
```

If subprocess unavailable, perform ast-grep analysis in main thread per file.

**Deep Tier (ast-grep + gh + QMD):**
- All Forge tier checks, plus:
- Use gh CLI to verify source repository matches documented version
- Cross-check type definitions against their source declarations
- Verify re-exported symbols trace to their original source

### 3. Build Coverage Results

Aggregate findings across all source files:

**Per-export status table:**

| Export | Type | Documented | Signature Match | File:Line | Status |
|--------|------|-----------|-----------------|-----------|--------|
| {name} | function/class/type | yes/no | yes/no/unverified | src/file.ts:42 | PASS/FAIL/WARN |

**Summary counts:**
- Total exports in source: {N}
- Documented in SKILL.md: {N}
- Missing documentation: {N}
- Signature mismatches: {N}
- Undocumented in SKILL.md but not in source (stale docs): {N}

### 4. Load Scoring Rules

Load `{scoringRulesFile}` to determine category scores:

- **Export Coverage:** (documented / total_exports) * 100
- **Signature Accuracy:** (matching_signatures / total_documented) * 100 (Forge/Deep only, "N/A" for Quick)
- **Type Coverage:** (documented_types / total_types) * 100 (Forge/Deep only, "N/A" for Quick)

### 5. Append Coverage Analysis to Output

Append the **Coverage Analysis** section to `{outputFile}`:

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Path:** {source_path}
**Files Analyzed:** {count}

### Export Coverage

| Export | Type | Documented | Signature | Source Location | Status |
|--------|------|-----------|-----------|-----------------|--------|
| ... per-export rows ... |

### Coverage Summary

- **Exports Found:** {N}
- **Documented:** {N} ({percentage}%)
- **Missing Documentation:** {N}
- **Signature Mismatches:** {N}
- **Stale Documentation:** {N}

### Category Scores

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Export Coverage | {N}% | {weight}% | {weighted}% |
| Signature Accuracy | {N}% | {weight}% | {weighted}% |
| Type Coverage | {N}% | {weight}% | {weighted}% |
```

### 6. Report Coverage Results

"**Coverage check complete.**

**{skill_name}** — {forge_tier} tier analysis of {file_count} source files:

- Exports: {documented}/{total} documented ({percentage}%)
- Signatures: {matching}/{total} accurate ({percentage}% or N/A for Quick)
- Types: {documented_types}/{total_types} covered ({percentage}% or N/A for Quick)

**{N} issues found** — details in Coverage Analysis section.

**Proceeding to coherence check...**"

### 7. Auto-Proceed

Display: "**Proceeding to coherence check...**"

#### Menu Handling Logic:

- After coverage analysis is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed validation step with no user choices
- Proceed directly to next step after coverage is analyzed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all source files have been analyzed, the Coverage Analysis section has been appended to {outputFile}, and category scores have been calculated, will you then load and read fully `{nextStepFile}` to execute coherence check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All source files analyzed at appropriate tier depth
- Every finding has file:line citation (Forge/Deep) or file-level reference (Quick)
- Per-export status table complete
- Category scores calculated per scoring rules
- Coverage Analysis section appended to output document
- Zero fabricated findings — all traceable to source

### ❌ SYSTEM FAILURE:

- Fabricating export names or signatures not in source code
- Skipping source files (DO NOT BE LAZY)
- Not scaling analysis depth to forge tier
- Not calculating category scores
- Reporting coverage without per-export evidence
- Hardcoding paths instead of using frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. Zero hallucination — every finding traces to code.

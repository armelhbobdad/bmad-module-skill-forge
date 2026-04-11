---
nextStepFile: './step-04-coherence-check.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
---

# Step 3: Coverage Check

## STEP GOAL:

Compare the exports, functions, classes, types, and interfaces documented in SKILL.md against the actual source code API surface. Identify missing documentation, undocumented exports, and signature mismatches. Analysis depth scales with forge tier.

## Rules

- Use subprocess optimization for per-file AST analysis when available; if unavailable, analyze sequentially
- For each source file, launch a subprocess for deep analysis — do not shortcut
- Coverage depth must match the detected forge tier

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 0. Check for Docs-Only Mode

**If all SKILL.md citations are `[EXT:...]` format (no local source citations):**

Set `docs_only_mode: true` in context for step-05 scoring. Coverage scoring adapts: instead of comparing SKILL.md against source code exports, compare SKILL.md documented items against themselves for internal completeness (every documented function has a description, parameters, and return type). Score based on documentation completeness rather than source coverage.

**Quick-tier weight adjustment:** If `confidence_tier` is also `"Quick"`, apply Quick-tier weight redistribution (zeroing Signature Accuracy and Type Coverage) as an additional step per `{scoringRulesFile}`.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

**If source-based skill:** Continue with standard coverage check below.

### 0b. Load Source Access Protocol

Load `{sourceAccessProtocol}` and follow both sections:
1. **Source API Surface Definition** — determines what counts as the public API for coverage denominator
2. **Source Access Resolution** — 5-state waterfall to determine how source files will be read and sets `analysis_confidence`

### 1. Extract Documented Exports from SKILL.md

<!-- Subagent delegation: read SKILL.md + references/*.md, return compact JSON inventory -->

Delegate reading of the skill under test to a subagent. The subagent receives the path to SKILL.md (and the `references/` directory path if it exists) and MUST:
1. Read SKILL.md
2. If a `references/` directory exists alongside SKILL.md and SKILL.md's `## Full` headings are absent or stubs, also read all `references/*.md` files
3. ONLY return this compact JSON inventory — no prose, no extra commentary:

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."]},
    {"name": "TypeName", "kind": "type", "fields": ["..."]},
    {"name": "CONST_NAME", "kind": "constant", "values": ["..."]},
    {"name": "useHook", "kind": "hook", "usage_signature": "..."}
  ],
  "capabilities": ["brief capability descriptions from the skill overview"],
  "references": ["references/api-reference.md", "references/type-definitions.md"],
  "cross_check_mismatches": [
    {
      "export": "functionName",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "description of the signature mismatch"
    }
  ]
}
```

**Parent uses this JSON summary as the documented inventory.** Do not load SKILL.md or references file contents into parent context.

**Split-body traversal** is handled inside the subagent: if `references/` exists and `## Full` headings are absent or stubs in SKILL.md, the subagent extends its scan to all `references/*.md` files and includes them in the `exports` array. After split-body, Tier 2 content (Full API Reference, Full Type Definitions) lives in reference files — the inventory must reflect the full skill content regardless of where it resides.

### 1b. Cross-Check Split-Body Consistency

**Only execute if the subagent's `references` array is non-empty** (detected during split-body traversal in Section 1). Skip silently otherwise.

The subagent has already read both SKILL.md body and `references/*.md` files. For each function, class, type, or interface that appears in BOTH the SKILL.md body AND any `references/*.md` file, instruct the subagent (or perform in the same subagent call from Section 1) to compare the documented signatures and include mismatches in its JSON output as a `cross_check_mismatches` array:

- **Parameters:** name, type, order, optionality
- **Return types:** exact type match
- **Description:** no contradictions (brief vs detailed is acceptable; conflicting semantics is not)

**SKILL.md body is authoritative.** When a mismatch is found, the reference file is the one that needs updating.

Parent reads `cross_check_mismatches` from the subagent JSON summary. Build the split-body consistency findings list:

```json
{
  "cross_check_mismatches": [
    {
      "export": "formatDate",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "SKILL.md shows (date: Date) => string, reference shows (date: Date, format?: string) => string"
    }
  ],
  "exports_cross_checked": 12,
  "mismatches_found": 1
}
```

Flag each mismatch as **High severity** — signature inconsistency between SKILL.md body and reference files undermines agent trust. These findings feed into the gap report (step-06).

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

**Stratified-scope denominator (monorepo curated subsets):** Before computing Export Coverage, check whether the Source Access Protocol's stratified-scope clause applies to this skill (see `{sourceAccessProtocol}` §Source API Surface Definition — "Stratified-scope monorepo packages"). When it applies:

1. **Prefer `metadata.json.stats.effective_denominator`** when present. Use it directly as `total_exports`.
2. **Otherwise re-derive at test time** from the brief's scope globs per the protocol. When the brief supplies `scope.tier_a_include`, re-derive from that narrower list; otherwise re-derive from `scope.include`. Use the resulting union count as `total_exports`.
3. **Run the denominator inflation check** defined in `{sourceAccessProtocol}` stratified-scope resolution step 3 whenever re-derivation fell back to `scope.include`. If the `scope.include` union exceeds the provenance-map entry count by more than 25%, emit the Medium-severity `denominator inflation — coarse scope.include union exceeds authored surface` gap and append it to the Coverage Analysis gap list.

Record the denominator source in the Coverage Analysis section as `Denominator: stratified ({effective_denominator | tier_a_include union | scope.include union}, {N} files matched)`. When stratified scope does not apply, use the standard barrel-based denominator and omit the stratified annotation.

**State 2 denominator validation:** When using provenance-map as the baseline (State 2), cross-reference the provenance-map entry count against `metadata.json`'s `exports[]` array before computing Export Coverage. If they diverge, use the union as the denominator per the source-access-protocol rules. Log the gap size if any. The stratified-scope rule above takes precedence when both conditions apply — compute the stratified denominator first, then validate the provenance-map entry count against it.

### 4b. Metadata Export-Count Coherence Cross-Check

After the denominator has been resolved (standard, stratified, or State 2), cross-check all available export-count sources for internal agreement. Picking the denominator silently when sources disagree is a known friction — the tester cannot tell whether to trust the pick, ignore the drift, or report it. Make it explicit: the tester MUST report a metadata drift finding whenever count sources diverge materially.

**Collect available counts (skip any that are absent):**

1. `metadata.json.stats.exports_public_api` — the declared public API count
2. `metadata.json.stats.exports_documented` — the declared documented count
3. `metadata.json.exports[]` array length — the enumerated export list
4. Provenance-map entry count (if `{forge_data_folder}/{skill_name}/provenance-map.json` exists)

**Divergence rule:** If two or more counts are present and any pair disagrees by more than 10% of the larger count, emit a **Medium**-severity gap titled `metadata drift — N conflicting export counts` where N is the number of sources collected. Enumerate every offending count in the gap body (e.g., `stats.exports_public_api=430, stats.exports_documented=320, exports[].length=82, provenance-map=222`). Classify under structural/metadata coherence regardless of naive/contextual mode. The gap is informational about data quality — it does not change the denominator chosen above, but it signals that upstream extraction or compilation produced inconsistent stats that a downstream update or re-compile should reconcile.

**When sources agree within 10%:** Skip silently. Do not emit a finding.

**When only one count is available:** Skip silently — there is nothing to cross-check.

Append any drift finding to the Coverage Analysis section's gap list (built in section 5) so it surfaces in the final test report alongside coverage and signature findings.

### 5. Append Coverage Analysis to Output

Append the **Coverage Analysis** section to `{outputFile}`:

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Access:** {analysis_confidence} (full | provenance-map | metadata-only | remote-only | docs-only)
**Source Path:** {source_path}
**Files Analyzed:** {count}
**Denominator:** {barrel | stratified ({effective_denominator | scope.include union}, {N} files matched)}

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

| Category | Score |
|----------|-------|
| Export Coverage | {N}% |
| Signature Accuracy | {N}% or N/A |
| Type Coverage | {N}% or N/A |

Note: Weight application is deferred to step-05 where all category weights are calculated after external validation availability is known.
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


---
nextStepFile: 'external-validators.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
migrationSectionRules: 'references/migration-section-rules.md'
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

### 2. Naive Mode: Concrete Structural Validation (H1)

Perform the following explicit checks (no hand-waving — each recipe is a shell recipe or a literal pattern). Severity assignments are binding; do not relax them.

**2.1 Required sections present.** For each required top-level H2, run `grep -n "^## {section}" SKILL.md`. A required section is satisfied if **any** synonym in its set matches:
- Description: `## Description` OR frontmatter `description` field — either satisfies
- Usage: `## Usage` OR `## Examples` OR `## Quick Start` OR `## Common Workflows`
- API surface: `## Exports` OR `## Key API Summary` OR `## API`
- **Zero matches across an entire synonym set → High severity** finding: `naive-coherence — missing required section: {section-set-name}`

Note: SKF-template skills ship with `## Quick Start`, `## Common Workflows`, and `## Key API Summary`. These are first-class synonyms — do not downgrade to Low on literal-name miss; accept them.

**2.2 Code fence balance.** Count triple-backtick fences with `grep -c '^```' SKILL.md`. **Odd count → High severity** finding: `naive-coherence — unbalanced code fence (unclosed block)`.

**2.3 Language tags on opening fences.** Only **opening** fences are required to carry a language tag; closing fences are bare by markdown convention and must NOT be flagged. Do not use a plain `grep -n '^```$' SKILL.md` — that flags every closing fence and produces one false positive per well-formed code block.

Use a stateful open/close scan (toggle `in_code` on each `^```` line; flag only the line where `in_code` transitions 0→1 with no trailing language tag):

```python
in_code = False
for i, line in enumerate(open('SKILL.md'), 1):
    s = line.rstrip('\n')
    if s.startswith('```'):
        if not in_code:
            if s == '```':
                print(f'{i}: bare opening fence')
            in_code = True
        else:
            in_code = False
```

**Each flagged opening fence → Medium severity** finding: `naive-coherence — opening code fence at line {N} missing language tag`.

**2.4 Exports cross-used in Usage section.** For each function name reported in the step 3 subagent inventory (`exports[].name` where `kind == "function"` or `kind == "method"`):
- `grep -c "{export.name}" SKILL.md` restricted to the Usage section (find the `## Usage` anchor from §2.1 and the next `^## ` anchor; count within that span).
- **Zero occurrences → High severity** finding: `naive-coherence — exported {kind} \`{name}\` is not referenced in the Usage section`. This catches the "documented but unused" failure mode that trivially fails discovery testing.

**2.5 Async/sync consistency.** For every export with `async` in its description prose (grep for `\basync\b` in the description segment), check the corresponding code example segment for `await` / `async` keywords:
- Description says async + example shows no `await` → **High severity** finding: `naive-coherence — \`{name}\` described as async but example lacks \`await\``
- Description says sync + example uses `await {name}` → **High severity** finding: `naive-coherence — \`{name}\` described as sync but example awaits it`

**2.6 Table syntax.** `grep -nE '^\|.*\|$' SKILL.md | head` — for each table row, normalize escaped pipes (`\|`) before splitting, then verify adjacent rows have the same column count. **Escaped pipes appear inside TypeScript union types and discriminated payloads** (e.g. `string \| undefined`) and must not inflate the count.

Recipe:

```bash
# Normalize `\|` to a placeholder, split on |, count, restore.
grep -nE '^\|.*\|$' SKILL.md \
  | sed 's/\\|/\x00/g' \
  | awk -F'|' '{print NR, NF-2}'   # -2 drops the empty leading/trailing fields
```

Or equivalent: hand off to a proper markdown-table parser. A plain `split on |` WILL produce false "column drift" findings on any table whose cells contain union types.

**Column-count drift → Medium severity** finding: `naive-coherence — table row at line {N} has {X} columns; neighboring rows have {Y}`.

**2.7 Scripts & Assets section.** If `{skillDir}/scripts/` or `{skillDir}/assets/` exists, `grep -n '^## Scripts' SKILL.md`:
- Directory exists AND no `## Scripts` section → **Medium severity** finding: `naive-coherence — scripts/assets directory exists but Scripts & Assets section missing` (per `{scoringRulesFile}`)

**Hard rule:** 0 findings across §§2.1–2.7 = naive coherence PASS. ≥1 finding = rerank per the severity rubric above; the count and severity list are appended to the Coherence Analysis output in §6.

Build the findings list:

```json
{
  "structural_issues": [
    {"type": "missing_section", "severity": "High", "detail": "No 'Usage' section found", "line": null},
    {"type": "unbalanced_fence", "severity": "High", "detail": "3 opening fences, 2 closing", "line": null},
    {"type": "export_not_in_usage", "severity": "High", "detail": "exported function `formatDate` never referenced in Usage section", "line": 42},
    {"type": "async_mismatch", "severity": "High", "detail": "`fetchData` described async but example lacks await", "line": 67}
  ],
  "issues_found": 4
}
```

**After naive coherence → Execute Section 2b if gate conditions met, then skip to Section 6 (Append Results)**

### 2b. Migration/Deprecation Verification (Mode-Independent)

Apply rules from `{migrationSectionRules}`. That file is the single source of
truth for the gate, scope, and case rules; §5b below applies the same rules on
the contextual path.

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

5. **Path containment (S8):** for every resolved reference target, compute its canonical path (`os.path.realpath`) and require that it lives inside `{skillDir}` OR inside `{source_path}` (the extraction tree recorded in metadata.json). References whose canonical path escapes both roots (e.g. `../../../etc/passwd`, absolute paths to unrelated dirs, symlink redirections outside the skill or its source) are **High severity** findings: `coherence — reference escapes skill/source sandbox: {raw_ref} → {canonical_path}`. Do NOT validate the target's contents for escaping references — the escape itself is the finding.

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

Apply rules from `{migrationSectionRules}`. Same rules as §2b — the reference
file is the single source of truth. Append findings to the coherence analysis
results.

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


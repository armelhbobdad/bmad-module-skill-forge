---
nextStepFile: 'external-validators.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
migrationSectionRules: 'references/migration-section-rules.md'
scanSkillMdStructureProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-skill-md-structure.py'
  - '{project-root}/src/shared/scripts/skf-scan-skill-md-structure.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Coherence Check

## STEP GOAL:

Validate internal consistency of the skill documentation. In contextual mode (stack skills): verify that all cross-references in SKILL.md point to real files, types match their declarations, and integration patterns are complete. In naive mode (individual skills): perform basic structural validation only.

### 1. Check Test Mode

Read `testMode` from `{outputFile}` frontmatter.

**IF naive mode → Execute Naive Coherence (Section 2)**
**IF contextual mode → Execute Contextual Coherence (Sections 3-5)**

### 2. Naive Mode: Concrete Structural Validation

Perform the following explicit checks (no hand-waving — most use a single deterministic script; severity assignments are binding; do not relax them).

**Resolve `{scanSkillMdStructureHelper}`** from `{scanSkillMdStructureProbeOrder}`; first existing path wins. HALT if no candidate exists.

**2.0 Run the structural scan.** Invoke `{scanSkillMdStructureHelper}` twice and parse the JSON outputs. These results back §§2.1, 2.2, 2.3, and 2.6 — do not re-implement those checks with grep/sed/awk loops.

```bash
uv run {scanSkillMdStructureHelper} scan {skill-md} --required-sections
uv run {scanSkillMdStructureHelper} scan {skill-md}
```

The first call returns `{ description: {satisfied, matched_synonym, tried[]}, usage: {...}, api_surface: {...} }`. The second returns `{ unbalanced_fences, fence_count, bare_opening_fences[{line,text}], table_drift[{line,section,expected_cols,actual_cols,row}] }`. Hold both JSON blobs for the checks below.

**2.1 Required sections present.** Read the first JSON blob from §2.0. For each of the three families (`description`, `usage`, `api_surface`):

- `satisfied: true` → no finding.
- `satisfied: false` AND family is `description` AND the SKILL.md frontmatter has a non-empty `description` field → no finding (the frontmatter alternative satisfies the family per the original rule).
- Otherwise → **High severity** finding: `naive-coherence — missing required section: {family}` (the `tried[]` list from the JSON identifies which synonyms were checked: `Description`/`Overview`/`Purpose`/`Summary` for description; `Usage`/`Examples`/`How to use`/`Quickstart`/`Quick Start`/`Getting Started`/`Common Workflows` for usage; `API`/`API Surface`/`Exports`/`Public API`/`Interface`/`Reference`/`Key API Summary` for api_surface).

The script matches case-insensitively and tolerates `##`/`###` heading levels. SKF-template skills' `## Quick Start`, `## Common Workflows`, and `## Key API Summary` are first-class synonyms baked into the script — they will surface with `satisfied: true` and the corresponding `matched_synonym` field.

**2.2 Code fence balance.** Read `unbalanced_fences` from the second JSON blob. **`true` → High severity** finding: `naive-coherence — unbalanced code fence (unclosed block)` (the JSON's `fence_count` may be cited in the detail).

**2.3 Language tags on opening fences.** Read `bare_opening_fences[]` from the second JSON blob. The script already runs the stateful open/close scan — closing fences are never reported. For each entry, emit a **Medium severity** finding: `naive-coherence — opening code fence at line {entry.line} missing language tag`.

**2.4 Exports cross-used in a usage-family section.** For each function name reported in the step 3 subagent inventory (`exports[].name` where `kind == "function"` or `kind == "method"`):
- Determine the usage-family search scope:
  - **Single-body skill** (no `references/` directory, or `## Full*` sections carry real content): the span from §2.1's `matched_synonym` anchor to the next `^## ` anchor.
  - **Split-body skill** (a `references/` directory exists alongside SKILL.md AND the SKILL.md `## Full*` sections are stubs/pointers): the union of EVERY usage-family heading present in SKILL.md (`Usage`/`Examples`/`How to use`/`Quickstart`/`Quick Start`/`Getting Started`/`Common Workflows`/`Key API Summary`), each from its anchor to the next `^## ` anchor, PLUS the full text of every file under `references/`.
- `grep -c "{export.name}"` across that scope and sum the counts.
- **Zero occurrences across the entire scope → High severity** finding: `naive-coherence — exported {kind} \`{name}\` is not referenced in any usage-family section or reference file`. This catches the "documented but unused" failure mode that trivially fails discovery testing. A method referenced in any usage-family section OR any `references/` file satisfies the check.

**2.5 Async/sync consistency.** For every export with `async` in its description prose (grep for `\basync\b` in the description segment), check the corresponding code example segment for `await` / `async` keywords:
- Description says async + example shows no `await` → **High severity** finding: `naive-coherence — \`{name}\` described as async but example lacks \`await\``
- Description says sync + example uses `await {name}` → **High severity** finding: `naive-coherence — \`{name}\` described as sync but example awaits it`

**2.6 Table syntax.** Read `table_drift[]` from the second JSON blob (§2.0). The script normalizes escaped pipes (`\|`, used inside TypeScript union types such as `string \| undefined`) before splitting and compares each row against its header's column count, so a plain `split on |` false-positive cannot occur here. For each entry, emit a **Medium severity** finding: `naive-coherence — table row at line {entry.line} has {entry.actual_cols} columns; header has {entry.expected_cols}` (the `entry.section` and `entry.row` fields populate the detail when present).

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

Delegate to a subagent that grep/regexes SKILL.md for reference patterns and returns ONLY this JSON shape — no prose, no commentary, no markdown fences: `{"references_found": [{"line": N, "type": "file-path|skill|type-import|integration-pattern|script-asset", "target": "..."}]}`. Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

For EACH reference found, delegate to a subagent that:

1. Checks if the target exists (file exists, skill exists, type is declared)
2. If target exists, validates the reference is accurate:
   - File path references: file exists at specified path
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
   - Script/asset references: verify the referenced file exists in the skill's `scripts/` or `assets/` directory
3. Returns ONLY this JSON shape per reference — no prose, no commentary, no markdown fences: `{"reference": "...", "line": N, "target_exists": <bool>, "type_match": <bool>, "signature_match": <bool>, "issues": ["..."]}`

Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, validate each reference in main thread.

4. **Scripts/assets directory check:** If a `scripts/` or `assets/` directory exists alongside SKILL.md, verify that a "Scripts & Assets" section (Section 7b) is present in SKILL.md. This directory-level check applies in both modes (naive mode performs it in Section 2; contextual mode performs it here alongside per-reference validation). Flag absence as Medium severity gap per `{scoringRulesFile}`.

5. **Path containment:** for every resolved reference target, compute its canonical path (`os.path.realpath`) and require that it lives inside `{skillDir}` OR inside `{source_path}` (the extraction tree recorded in metadata.json). References whose canonical path escapes both roots (e.g. `../../../etc/passwd`, absolute paths to unrelated dirs, symlink redirections outside the skill or its source) are **High severity** findings: `coherence — reference escapes skill/source sandbox: {raw_ref} → {canonical_path}`. Do NOT validate the target's contents for escaping references — the escape itself is the finding.

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

Update stepsCompleted, then load and execute {nextStepFile}.


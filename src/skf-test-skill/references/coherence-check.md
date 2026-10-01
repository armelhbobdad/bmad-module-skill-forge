---
nextStepFile: 'external-validators.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
coherenceAggregationScript: 'scripts/aggregate-coherence.py'
locateExportSegmentsScript: 'scripts/locate-export-segments.py'
migrationSectionRules: 'references/migration-section-rules.md'
# §6 records every gap this step finds in the run's gap ledger, which the
# hard gate (step 4c) reads and the Gap Report is rendered from.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
scanSkillMdStructureProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-skill-md-structure.py'
  - '{project-root}/src/shared/scripts/skf-scan-skill-md-structure.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Coherence Check

## STEP GOAL:

Validate internal consistency of the skill documentation. In contextual mode (stack skills): verify that all cross-references in SKILL.md point to real files, types match their declarations, and integration patterns are complete. In naive mode (individual skills): perform basic structural validation only.

Every HALT in this step releases the run lock first (SKILL.md Workflow Rules).

### 1. Check Test Mode

Read `testMode` from `{outputFile}` frontmatter.

**IF naive mode → Execute Naive Coherence (Section 2)**
**IF contextual mode → Execute Contextual Coherence (Sections 3-5)**

### 2. Naive Mode: Concrete Structural Validation

Perform the following explicit checks (no hand-waving — most use a single deterministic script; severity assignments are binding; do not relax them).

**Resolve `{scanSkillMdStructureHelper}`** from `{scanSkillMdStructureProbeOrder}`; first existing path wins. If no candidate exists, release the run lock (SKILL.md Workflow Rules), then HALT.

**2.0 Run the structural scan.** Invoke `{scanSkillMdStructureHelper}` twice and parse the JSON outputs. These results back §§2.1, 2.2, 2.3, and 2.6 — do not re-implement those checks with grep/sed/awk loops.

```bash
uv run {scanSkillMdStructureHelper} scan {skill-md} --required-sections
uv run {scanSkillMdStructureHelper} scan {skill-md}
```

The first call returns `{ description: {satisfied, matched_synonym, tried[]}, usage: {...}, api_surface: {...} }`. The second returns `{ unbalanced_fences, fence_count, bare_opening_fences[{line,text}], table_drift[{line,section,expected_cols,actual_cols,row}] }`. Hold both JSON blobs for the checks below.

**2.1 Required sections present.** Read the first JSON blob from §2.0. For each of the three families (`description`, `usage`, `api_surface`):

- `satisfied: true` → no finding.
- `satisfied: false` AND family is `description` AND the SKILL.md frontmatter has a non-empty `description` field → no finding (the frontmatter alternative satisfies the family per the original rule).
- Otherwise → **High severity** finding: `naive-coherence: missing required section: {family}` (the `tried[]` list from the JSON identifies which synonyms were checked: `Description`/`Overview`/`Purpose`/`Summary` for description; `Usage`/`Usage Patterns`/`Examples`/`How to use`/`Quickstart`/`Quick Start`/`Getting Started`/`Common Workflows`/`Adoption Steps` for usage; `API`/`API Surface`/`Exports`/`Key Exports`/`Public API`/`Interface`/`Reference`/`Key API Summary`/`Pattern Surface` for api_surface).

The script matches case-insensitively and tolerates `##`/`###` heading levels. SKF-template skills' headings are first-class synonyms baked into the script — the Deep/create-skill `## Quick Start`, `## Common Workflows`, and `## Key API Summary`, the quick-skill `## Usage Patterns` and `## Key Exports`, and the reference-app overrides `## Adoption Steps` (usage) and `## Pattern Surface` (api_surface) — so they all surface with `satisfied: true` and the corresponding `matched_synonym` field.

**2.2 Code fence balance.** Read `unbalanced_fences` from the second JSON blob. **`true` → High severity** finding: `naive-coherence: unbalanced code fence (unclosed block)` (the JSON's `fence_count` may be cited in the detail).

**2.3 Language tags on opening fences.** Read `bare_opening_fences[]` from the second JSON blob. The script already runs the stateful open/close scan, so closing fences are never reported. For each entry, emit a **Medium severity** finding: `naive-coherence: opening code fence at line {entry.line} missing language tag`.

**2.4 Exports cross-used in a usage-family section.** For each function name in the validated inventory step 3 wrote to `{run_dir}/inventory.json` (`exports[].name` where `kind == "function"` or `kind == "method"`):
- Determine the usage-family search scope:
  - **Single-body skill** (no `references/` directory, or `## Full*` sections carry real content): the span from §2.1's `matched_synonym` anchor to the next `^## ` anchor.
  - **Split-body skill** (a `references/` directory exists alongside SKILL.md AND the SKILL.md `## Full*` sections are stubs/pointers): the union of EVERY usage-family heading present in SKILL.md (`Usage`/`Usage Patterns`/`Examples`/`How to use`/`Quickstart`/`Quick Start`/`Getting Started`/`Common Workflows`/`Adoption Steps`/`Key API Summary`/`Pattern Surface`/`Key Exports`), each from its anchor to the next `^## ` anchor, PLUS the full text of every file under `references/`.
- `grep -c "{export.name}"` across that scope and sum the counts.
- **Zero occurrences across the entire scope → Medium severity** finding: `naive-coherence: exported {kind} \`{name}\` is not referenced in any usage-family section or reference file`. This catches the "documented but unused" failure mode that trivially fails discovery testing. Like a missing export, it is a completeness gap, so it does not block the hard gate. A method referenced in any usage-family section OR any `references/` file satisfies the check.

**2.5 Async/sync consistency.** `{locateExportSegmentsScript}` reports the facts: for each export the step 3 inventory lists with `kind` `function` or `method`, where the skill describes it (`descriptions[]`: the heading sections, table rows, list items and paragraphs that name it in code, and the signature lines that declare it) and each call to it in fenced code, with whether the call awaits it. It reads the names from the validated inventory file itself, keeping the `function` and `method` entries, so no name is copied by hand. Skip this check when the inventory has no such export; otherwise run the script (it resolves relative to the skill root):

```bash
uv run {locateExportSegmentsScript} --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}"
```

The script judges no meaning. For each `exports[]` entry, read its `descriptions[]` and decide what they assert about **this** export. The word `async` in a description decides nothing:

- **async**: the caller must await what it returns (a promise, a coroutine or a future), as its signature or its description says. A Kotlin `suspend` function needs no `await`, so it makes no async claim here.
- **sync**: it returns its result directly, for example as the blocking counterpart of an async export.
- **no claim**: nothing says how it returns. A description that names a paired sync or async variant (`readFileSync` as "the sync counterpart of the async `readFile`"), or says async about another API, asserts nothing about this export.

Then, for each export:

- **async**, no call is awaited (`awaitedCount` is 0) and no unawaited call hands its result on → **High severity** finding: `naive-coherence: \`{name}\` described as async but example lacks \`await\`` (cite the first call's `file` and `line`). A call hands its result on when its `chainedMember` waits for it (`then`, `catch`, `join`, `get`), the example returns it (`return fetchData(x)` in an async function) or stores it and awaits it later: read the call lines before raising the finding.
- **sync** and `awaitedCount` is above 0 → **High severity** finding: `naive-coherence: \`{name}\` described as sync but example awaits it` (cite the first awaited call).
- Otherwise no finding. The names in `notCalled[]` appear in no example, so they raise none.

**2.6 Table syntax.** Read `table_drift[]` from the second JSON blob (§2.0). The script normalizes escaped pipes (`\|`, used inside TypeScript union types such as `string \| undefined`) before splitting and compares each row against its header's column count, so a plain `split on |` false-positive cannot occur here. For each entry, emit a **Medium severity** finding: `naive-coherence: table row at line {entry.line} has {entry.actual_cols} columns; header has {entry.expected_cols}` (the `entry.section` and `entry.row` fields populate the detail when present).

**2.7 Scripts & Assets section.** If `{skillDir}/scripts/` or `{skillDir}/assets/` exists, `grep -n '^## Scripts' SKILL.md`:
- Directory exists AND no `## Scripts` section → **Medium severity** finding: `naive-coherence: scripts/assets directory exists but Scripts & Assets section missing` (per `{scoringRulesFile}`)

**Hard rule:** 0 findings across §§2.1–2.7 = naive coherence PASS. ≥1 finding = rerank per the severity rubric above; the count and severity list go into the Coherence Analysis section §6 writes.

Build the findings list:

```json
{
  "structural_issues": [
    {"type": "missing_section", "severity": "High", "detail": "No 'Usage' section found", "line": null},
    {"type": "unbalanced_fence", "severity": "High", "detail": "3 opening fences, 2 closing", "line": null},
    {"type": "export_not_in_usage", "severity": "Medium", "detail": "exported function `formatDate` never referenced in Usage section", "line": 42},
    {"type": "async_mismatch", "severity": "High", "detail": "`fetchData` described async but example lacks await", "line": 67}
  ],
  "issues_found": 4
}
```

**After naive coherence → Execute Section 2b if gate conditions met, then skip to Section 6 (Write Results)**

### 2b. Migration/Deprecation Verification (Mode-Independent)

Apply rules from `{migrationSectionRules}`. That file is the single source of
truth for the gate, scope, and case rules; §5b below applies the same rules on
the contextual path.

**After Section 2b (naive path) → Skip to Section 6 (Write Results)**

### 3. Contextual Mode: Extract References

Scan SKILL.md for all cross-references:

**Reference types to extract:**
- File path references (`./path/to/file.ts`, `../shared/types.ts`)
- Skill references (`See SKILL.md for {other-skill}`, `Integrates with {package}`)
- Type imports (`import { Type } from './module'`)
- Integration pattern references (middleware chains, plugin hooks, shared state)
- Script/asset references (`scripts/{file}`, `assets/{file}`) in SKILL.md body

Delegate to a subagent that grep/regexes SKILL.md for reference patterns and returns only this JSON shape — no prose, no commentary, no markdown fences: `{"references_found": [{"line": N, "type": "file-path|skill|type-import|integration-pattern|script-asset", "target": "..."}]}`. Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

For EACH reference found, delegate to a subagent that:

1. Checks if the target exists (file exists, skill exists, type is declared)
2. If target exists, validates the reference is accurate:
   - File path references: file exists at specified path
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
   - Script/asset references: verify the referenced file exists in the skill's `scripts/` or `assets/` directory
3. Returns only this JSON shape per reference — no prose, no commentary, no markdown fences: `{"reference": "...", "line": N, "target_exists": <bool>, "type_match": <bool>, "signature_match": <bool>, "issues": ["..."]}`

Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, validate each reference in main thread.

Classify each result against the Gap Severity table (`{scoringRulesFile}`): a reference whose `target_exists` is false is a broken reference, a Critical `broken-reference` gap (a `scripts/` or `assets/` file the skill names that is not there included); a reference whose target exists but whose `type_match` or `signature_match` is false, or whose `issues` is not empty, is an inaccurate reference, a High `inaccurate-reference` gap. Its Source is `SKILL.md:{line}`, and its Issue is the result's `issues`. §6 records each one.

4. **Scripts/assets directory check:** If a `scripts/` or `assets/` directory exists alongside SKILL.md, verify that a "Scripts & Assets" section (Section 7b) is present in SKILL.md. This directory-level check applies in both modes (naive mode performs it in Section 2; contextual mode performs it here alongside per-reference validation). Its absence is a Medium `scripts-assets` gap (`{scoringRulesFile}`).

5. **Path containment:** for every resolved reference target, compute its canonical path (`os.path.realpath`) and require that it lives inside `{skillDir}`, inside `{source_path}` (the extraction tree recorded in metadata.json), OR — for stack skills — inside `{skills_output_folder}`. The third root applies only here in contextual mode: a stack's constituent cross-references legitimately resolve to `skills/{name}/active` under `{skills_output_folder}`, which lies outside `{skillDir}`, and a stack's metadata.json records no single `source_path` to anchor them. References whose canonical path escapes all applicable roots (e.g. `../../../etc/passwd`, absolute paths to unrelated dirs, symlink redirections outside the skill, its source, or — for a stack — the skills output tree) are **High severity** findings: `coherence — reference escapes skill/source sandbox: {raw_ref} → {canonical_path}`. Canonicalization happens before the root check, so a symlink that points outside every applicable root is still caught. Do not validate the target's contents for escaping references — the escape itself is the finding.

### 5. Contextual Mode: Check Integration Pattern Completeness

For stack skills, verify integration patterns are complete:

- **All documented integration points carry the wiring evidence of the stack's mode** (defined below; a fenced code example is not required)
- **Shared types are consistently used across referenced components**
- **Middleware/plugin chains show complete flow, not fragments**
- **Event handlers reference valid event types**

**Integration points.** Each Cross-Cutting Patterns entry and each Library Pair Integrations entry in the stack's Integration Patterns section is one integration point, and `patterns_documented` counts them. The Hub Library Connections list that create-stack-skill adds after them only summarizes each hub library's partners, so its bullets are not integration points: this section does not score them and `patterns_documented` does not count them.

**Wiring evidence (first criterion).** create-stack-skill gives an integration entry no slot for a code example: the entry records a type, the wiring evidence of the stack's mode and a confidence label, so the first criterion reads that evidence. Take the stack's mode from the Confidence labels of its integration entries: the stack is compose-mode when any of them carries the `[composed]` marker (alone or extended, as in `[composed, +T2 annotations]`) or `[inferred from shared domain]`, the markers create-stack-skill puts on every compose-mode integration; otherwise it is code-mode. An integration point meets the first criterion when its entry carries the evidence of its stack's mode:

- **Code mode:** at least one `file:line` citation (a source file path with a line number) where the libraries connect in the codebase, and, for a library-pair entry, a `**Key files:**` line that names at least one file.
- **Compose mode:** one `[from skill: {skill name}]` line for each constituent skill the entry joins, citing something that skill exports. For a skill that exports functions, that is an exported function signature, the `[from skill: {skill name}] {exported_function_signature}` line of the Integration Evidence Format in `skf-create-stack-skill/references/compose-mode-rules.md`. For any other constituent (a skill whose `scope_type` is `reference-app` or `docs-only`, or whose exports are not functions), it is the export, pattern surface or documented contract the line quotes. A `[from skill: …]` line that cites nothing the skill exports does not count.

A fenced code block is not required in either mode: an entry that carries its mode's evidence meets the criterion without one, and a code block does not stand in for missing evidence. When an entry fails the first criterion, name the missing evidence in its `incomplete_patterns` issue, for example `no file:line citation` or `no [from skill: …] line for {skill name}`.

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

Each `incomplete_patterns` entry is an incomplete integration pattern, a Medium `integration-pattern` gap, with its Source at `SKILL.md:{line}` and the missing evidence as its Issue; §6 records it.

**Zero integration patterns:** If no integration patterns are documented in SKILL.md (e.g., a contextual-mode skill that uses shared types but has no middleware chains, plugin hooks, or event flows): record `patterns_documented: 0`, `patterns_complete: 0`. The coherence score then uses reference validity alone: with no integration patterns, §5c's script makes combined coherence equal reference validity.

### 5b. Migration/Deprecation Verification (Contextual Path)

Apply rules from `{migrationSectionRules}`. Same rules as §2b — the reference
file is the single source of truth. Append findings to the coherence analysis
results.

### 5c. Calculate Coherence Scores

**Contextual mode only.** The reference-validity ratio, the integration-completeness ratio, and their weighted mean are pure arithmetic: the judgment (which references are valid in §4, which patterns are complete in §5) has already happened. Do not compute these percentages by hand; `{coherenceAggregationScript}` aggregates them and is the one home of the formula and its weights.

Tally the counts from the §4 per-reference JSON (`valid_references` = references with `target_exists && type_match && signature_match && no issues`; `total_references` = references extracted in §3) and the §5 integration JSON (`patterns_documented`, `patterns_complete`), then invoke:

```bash
echo '{"valid_references": <V>, "total_references": <T>, "patterns_documented": <PD>, "patterns_complete": <PC>}' | uv run {coherenceAggregationScript} --stdin --output "{run_dir}/coherence.json"
```

`--output` also writes the result to the run folder, where step 5 hands it to the scoring script. Parse its output and read:
- `referenceValidity`: reference-validity percentage
- `integrationCompleteness`: integration-completeness percentage (`null` when no patterns are documented)
- `combinedCoherence`: the combined coherence percentage, the `coherence` score step 5 reads from `{run_dir}/coherence.json`

The script handles both edge cases the formula requires: `patterns_documented == 0` → `combinedCoherence` equals `referenceValidity` (no divide-by-zero); `total_references == 0` → `referenceValidity` is 100.0 (no references means no broken references). These values fill the `{percentage}%` placeholders in the output template loaded in Section 6.

### 6. Write the Coherence Analysis Section

Load `{outputFormatsFile}` and use the appropriate Coherence Analysis section format (naive or contextual) to write the findings in place of the template's `## Coherence Analysis` heading and the placeholder comment under it, in `{outputFile}`.

Then record every coherence gap in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. Each gap is one record in the Ledger Record Format of `{outputFormatsFile}`, with the severity and category the Gap Severity table gives it:

- **Naive mode:** the §2.1, §2.2 and §2.5 findings are High `structural` gaps and the §2.3, §2.4 and §2.6 findings Medium `structural` gaps, each titled with its `naive-coherence:` text and with its Source at `SKILL.md:{line}` when it has a line (else `SKILL.md`); the §2.7 finding is a Medium `scripts-assets` gap. The split-body rows of the Reference Consistency table are not recorded here: coverage-check §1b recorded them.
- **Contextual mode:** each §4 broken or inaccurate reference and the §4 scripts/assets gap, each §4 path-containment escape (a High `reference-escape` gap, Source `SKILL.md:{line}`), and each §5 incomplete integration pattern.
- **Both modes (§2b / §5b):** a migration section finding: Case 1 and Case 3 are Medium `migration-section` gaps (a Low `migration-section` gap when the reviewer downgraded Case 3 with an inline justification), and Case 2 is an Info `migration-section` gap.

Write the records as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without (`{gapLedgerScript}` resolves relative to the skill root).

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on its JSON:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0) and run the command again.
- Exit 1: HALT with the script's `error`.

### 7. Report Coherence Results

Report the coherence result to the user, then proceed to external validation:

- **Naive mode:** the count of structural issues found (the coherence category is not scored — its weight redistributes to coverage).
- **Contextual mode:** the reference-validity ratio, the integration-completeness ratio, the combined coherence percentage, and the issue count — full details are in the Coherence Analysis section.

Append `'coherence-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.


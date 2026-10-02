---
nextStepFile: 'external-validators.md'
outputFile: '{report_file}'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
coherenceAggregationScript: 'scripts/aggregate-coherence.py'
locateExportSegmentsScript: 'scripts/locate-export-segments.py'
migrationSectionRules: 'references/migration-section-rules.md'
# §6 records every gap this step finds in the run's gap ledger, which the
# hard gate (step 4c) reads and the Gap Report is rendered from.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
# Resolve `{scanSkillMdStructureHelper}` to the first existing path (§1): both
# modes take their structural facts, export usage counts and reference
# checks from it, so no step greps SKILL.md by hand.
scanSkillMdStructureProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-skill-md-structure.py'
  - '{project-root}/src/shared/scripts/skf-scan-skill-md-structure.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Coherence Check

## STEP GOAL:

Validate internal consistency of the skill documentation. In contextual mode (stack skills): verify that all cross-references in SKILL.md point to real files, types match their declarations, and integration patterns are complete. In naive mode (individual skills): perform basic structural validation only.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Check Test Mode

Read `testMode` from `{outputFile}` frontmatter.

**Resolve `{scanSkillMdStructureHelper}`** from `{scanSkillMdStructureProbeOrder}`; first existing path wins. Both modes run it. If no candidate exists, HALT (`halt_reason: "helper-missing"`, phase `coherence-check:scan`). Any command of it below that exits non-zero: HALT with its stderr (`halt_reason: "helper-failed"`, phase `coherence-check:scan`).

**IF naive mode → Execute Naive Coherence (Section 2)**
**IF contextual mode → Execute Contextual Coherence (Sections 3-5)**

### 2. Naive Mode: Concrete Structural Validation

Perform the following explicit checks (no hand-waving — most use a single deterministic script; severity assignments are binding; do not relax them).

**2.0 Run the structural scan.** Invoke `{scanSkillMdStructureHelper}` (§1) twice, saving each output to the run folder. These results back §§2.1, 2.2, 2.3, 2.6 and 2.7: do not re-implement those checks with grep/sed/awk loops.

```bash
uv run {scanSkillMdStructureHelper} scan "{resolved_skill_package}/SKILL.md" --required-sections > "{run_dir}/required-sections.json"
uv run {scanSkillMdStructureHelper} scan "{resolved_skill_package}/SKILL.md" > "{run_dir}/structure.json"
```

The first call returns `{ description: {satisfied, matched_synonym, tried[]}, usage: {...}, api_surface: {...}, frontmatter_description, outline[{line,level,text}] }`. The second returns `{ unbalanced_fences, fence_count, bare_opening_fences[{line,text}], table_drift[{line,section,expected_cols,actual_cols,row}], scripts_assets{folders[],section,missing} }`. Hold both JSON blobs, which the files keep, for the checks below.

**2.1 Required sections present.** Read the first JSON blob from §2.0. For each of the three families (`description`, `usage`, `api_surface`):

- `satisfied: true` → no finding.
- `satisfied: false`, family `description` and `frontmatter_description: true` (a non-empty frontmatter `description` satisfies the family) → no finding.
- `satisfied: false` otherwise: read `outline`, each heading of the body with its line. When one heading's section serves the family (it shows how to call the library, for `usage`; it lists the library's exports, for `api_surface`; it says what the library is for, for `description`), there is no finding: name that heading and its line in the Coherence Analysis, and pass the family to §6 as `--served`. Otherwise → **High severity** finding: `naive-coherence: missing required section: {family}`.

The script matches the full heading text, case-insensitively, at any heading level, outside the frontmatter and fenced code. Its synonyms, `tried[]`, include every SKF template and override heading, so a skill built from a template reports `satisfied: true` and the `matched_synonym`.

**2.2 Code fence balance.** Read `unbalanced_fences` from the second JSON blob. **`true` → High severity** finding: `naive-coherence: unbalanced code fence (unclosed block)` (the JSON's `fence_count` may be cited in the detail).

**2.3 Language tags on opening fences.** Read `bare_opening_fences[]` from the second JSON blob. The script already runs the stateful open/close scan, so closing fences are never reported. For each entry, emit a **Medium severity** finding: `naive-coherence: opening code fence at line {entry.line} missing language tag`.

**2.4 Exports cross-used in a usage-family section.** The scanner counts how often each function and method export of the validated inventory (the file step 3 wrote) is used in the usage-family scope, so no name is grepped by hand:

```bash
uv run {scanSkillMdStructureHelper} usage-scope "{resolved_skill_package}/SKILL.md" --exports "{run_dir}/inventory.json" --kinds function,method [--body single] > "{run_dir}/usage-scope.json"
```

The script decides split-body from the `references/` folder alone; whether the `## Full*` sections are stubs is your judgment, so pass `--body single` when a `references/` directory exists but those sections carry real content. Read `zero_usage[]` from the output:
- **Zero occurrences across the entire scope → Medium severity** finding, one per `zero_usage[]` entry: `naive-coherence: exported {kind} \`{name}\` is not referenced in any usage-family section or reference file`. This catches the "documented but unused" failure mode that trivially fails discovery testing. Like a missing export, it is a completeness gap, so it does not block the hard gate.

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

**2.7 Scripts & Assets section.** Read `scripts_assets` from the second JSON blob (§2.0): `folders` names the `scripts/` and `assets/` folders beside SKILL.md, and `section` the first heading that starts with `Scripts` (null when there is none).
- `missing` is true (a folder exists AND no Scripts heading) → **Medium severity** finding: `naive-coherence: scripts/assets directory exists but Scripts & Assets section missing` (per `{scoringRulesFile}`)

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

SKILL.md's cross-references come in two kinds, and each has one owner:

- **File-path and script/asset references**: every markdown link to a file (`[types](src/types.ts)`, `[guide](references/guide.md)`) and every `references/`, `scripts/` or `assets/` path mentioned in prose or inline code (`references/{file}.md`, `scripts/{file}`, `assets/{file}`), by the scanner's Reference extraction rules. Whether the target exists, and where it really lives, has one right answer, so the scanner extracts them and checks them. Any other path written outside a link (`../shared/types.ts` in inline code, an import specifier) is not checked: it usually names a file in the reader's project or a module, not one the skill ships:

  ```bash
  uv run {scanSkillMdStructureHelper} reference-check "{resolved_skill_package}/SKILL.md" [--source-root "{source_path}"] [--skills-root "{skills_output_folder}"] > "{run_dir}/references.json"
  ```

  Pass `--source-root` when metadata.json records the extraction tree (`{source_path}`), and `--skills-root` for a stack skill: a stack's constituent cross-references legitimately resolve to `skills/{name}/active` under `{skills_output_folder}`, which lies outside `{skillDir}`, and a stack's metadata.json records no single `source_path` to anchor them. The scanner resolves each target against the SKILL.md folder through every symlink (`os.path.realpath`) before the root check, so a symlink that points outside every root is still caught, and gives it a `status`: `ok` (inside a root, present), `missing` (inside a root, nothing there) or `escapes` (outside every root: `../../../etc/passwd`, an absolute path to an unrelated folder, a symlink redirection outside the skill, its source or a stack's skills tree). Do not check these targets again by hand or through subagents, and do not validate an escaping target's contents: the escape itself is the finding.
- **Skill references, type imports and integration-pattern references** (`See SKILL.md for {other-skill}`, `Integrates with {package}`, `import { Type } from './module'`, middleware chains, plugin hooks, shared state): whether one is accurate takes judgment. Delegate to a subagent that reads SKILL.md and returns only this JSON shape (no prose, no commentary, no markdown fences): `{"references_found": [{"line": N, "type": "skill|type-import|integration-pattern", "target": "..."}]}`. Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

The scanned references need no further check: `{run_dir}/references.json` holds their statuses.

Delegate the references §3's subagent found, in one batch, to a subagent that, for each one:

1. Checks if the target exists (the skill exists in the skills output folder, the type is declared, the integration point is in the code)
2. If the target exists, validates the reference is accurate:
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
3. Returns only a JSON array, one object per reference, with no prose, no commentary and no markdown fences: `{"reference": "...", "line": N, "target_exists": <bool>, "type_match": <bool>, "signature_match": <bool>, "issues": ["..."]}`

Save its response, as it came back, to `{run_dir}/judged-references.json` with the Write tool (no file when §3 found no such reference). If subagent unavailable, validate each reference in main thread and save the same array. §5c counts the valid references from both files, and classifies the invalid ones.

When `scripts_assets.missing` in `{run_dir}/references.json` is true (a `scripts/` or `assets/` folder beside SKILL.md, and no Scripts & Assets section), it is a Medium `scripts-assets` gap, as in naive mode §2.7; §6 records it from that file.

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

Build integration completeness findings, and save them to `{run_dir}/integration.json` with the Write tool (§5c reads the file):

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

The script counts the references itself, from the per-reference files of §3 and §4, and reads the pattern counts from the §5 file:

```bash
uv run {coherenceAggregationScript} --references "{run_dir}/references.json" [--judged "{run_dir}/judged-references.json"] --integration "{run_dir}/integration.json" --output "{run_dir}/coherence.json"
```

Exit 2 (`INVALID_INPUT`): a file does not hold the shape §3 to §5 describe; correct it (re-dispatch the §4 subagent once for its file) and run the command again. Exit 1: a file is missing or is not JSON; write it again. A second failure: HALT with its `error` (`halt_reason: "helper-failed"`, phase `coherence-check:aggregate`).

`--output` also writes the result to the run folder, where step 5 hands it to the scoring script. Parse its output and read:
- `referenceValidity`: reference-validity percentage
- `integrationCompleteness`: integration-completeness percentage (`null` when no patterns are documented)
- `combinedCoherence`: the combined coherence percentage, the `coherence` score step 5 reads from `{run_dir}/coherence.json`

The script handles both edge cases the formula requires: `patterns_documented == 0` → `combinedCoherence` equals `referenceValidity` (no divide-by-zero); `total_references == 0` → `referenceValidity` is 100.0 (no references means no broken references). These values fill the `{percentage}%` placeholders in the output template loaded in Section 6. Its `invalidReferences[]` lists each invalid reference with its `status`, which §6 records.

### 6. Write the Coherence Analysis Section

Load `{outputFormatsFile}` and use the appropriate Coherence Analysis section format (naive or contextual) to write the findings in place of the template's `## Coherence Analysis` heading and the placeholder comment under it, in `{outputFile}`.

Then record every coherence gap in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. `{gapLedgerScript}` (it resolves relative to the skill root) writes the record of each gap a script found from that script's file, with the severity and category the Gap Severity table gives it and a fixed title, Source and Remediation. Run the commands of this run's mode:

- **Naive mode:** the §2.1, §2.2 and §2.5 findings are High `structural` gaps and the §2.3, §2.4 and §2.6 findings Medium `structural` gaps; the §2.7 finding is a Medium `scripts-assets` gap. The scan files give all but §2.5's, with one `--served` for each family §2.1 found served by another heading:

  ```bash
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from structure --input "{run_dir}/required-sections.json" --input "{run_dir}/structure.json" --input "{run_dir}/usage-scope.json" [--served <family>]...
  ```

- **Contextual mode:** each §5c `invalidReferences[]` entry by its `status` (`missing` is a Critical `broken-reference` gap, a missing `scripts/` or `assets/` file included; `inaccurate` a High `inaccurate-reference` gap; `escapes` a High `reference-escape` gap) and the §4 scripts/assets gap:

  ```bash
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from coherence --input "{run_dir}/coherence.json"
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from structure --input "{run_dir}/references.json"
  ```

Then write the records no script wrote, each in the Ledger Record Format of `{outputFormatsFile}`: the §2.5 findings, titled with their `naive-coherence:` text and with their Source at `SKILL.md:{line}`; each §5 incomplete integration pattern; and in both modes a §2b / §5b migration section finding (Case 1 and Case 3 are Medium `migration-section` gaps, a Low `migration-section` gap when the reviewer downgraded Case 3 with an inline justification, and Case 2 is an Info `migration-section` gap). The split-body rows of the Reference Consistency table are not recorded here: coverage-check §1b recorded them. Write them as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without.

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on the JSON of each command:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0), or the file or flag the `error` names, and run the command again.
- Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `coherence-check:ledger`).

### 7. Report Coherence Results

Report the coherence result to the user, then proceed to external validation:

- **Naive mode:** the count of structural issues found (the coherence category is not scored — its weight redistributes to coverage).
- **Contextual mode:** the reference-validity ratio, the integration-completeness ratio, the combined coherence percentage, and the issue count — full details are in the Coherence Analysis section.

Append `'coherence-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.


---
nextStepFile: 'external-validators.md'
outputFile: '{report_file}'
outputFormatsFile: 'assets/output-section-formats.md'
coherenceNaiveFile: 'references/coherence-naive.md'
coherenceContextualFile: 'references/coherence-contextual.md'
coherenceAggregationScript: 'scripts/aggregate-coherence.py'
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

**IF naive mode → load `{coherenceNaiveFile}` and follow it (§2 and §2b), then continue at §6.**
**IF contextual mode → load `{coherenceContextualFile}` and follow it (§3 to §5c), then continue at §6.**

### 6. Write the Coherence Analysis Section

A §2 to §5c below is a section of the mode file §1 loaded.

Load `{outputFormatsFile}` and use the Coherence Analysis section format of this run's mode. Its tables come from the run files: first run the render of the mode (it resolves relative to the skill root), the naive one with the same `--served` as its append below.

- **Naive mode:**

  ```bash
  uv run {gapLedgerScript} render --from structure --input "{run_dir}/required-sections.json" --input "{run_dir}/structure.json" --input "{run_dir}/usage-scope.json" [--served <family>]...
  ```

- **Contextual mode:**

  ```bash
  uv run {coherenceAggregationScript} render --coherence "{run_dir}/coherence.json" --references "{run_dir}/references.json" [--judged "{run_dir}/judged-references.json"]
  ```

Exit 0: write the format, with the render's output unchanged where it places it, in place of the template's `## Coherence Analysis` heading and the placeholder comment under it, in `{outputFile}`. Exit 2 is a usage error, or a file the render refuses (a `coherence.json` whose counts differ from the files is §5c's to write again): correct it and run the render again. Exit 1, or a second exit 2: HALT with its error (`halt_reason: "helper-failed"`, phase `coherence-check:render`).

Then record every coherence gap in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. `{gapLedgerScript}` (it resolves relative to the skill root) writes the record of each gap a script found from that script's file, with the severity and category the Gap Severity table gives it and a fixed title, Source and Remediation. Run the commands of this run's mode:

- **Naive mode:** the §2.1, §2.2 and §2.5 findings are High `structural` gaps and the §2.3, §2.4 and §2.6 findings Medium `structural` gaps; the §2.7 finding is a Medium `scripts-assets` gap. The scan files give all but §2.5's, with one `--served` for each family §2.1 found served by another heading:

  ```bash
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from structure --input "{run_dir}/required-sections.json" --input "{run_dir}/structure.json" --input "{run_dir}/usage-scope.json" [--served <family>]...
  ```

- **Contextual mode:** each §5c `invalidReferences[]` entry by its `status` (`missing` is a Critical `broken-reference` gap, a missing `scripts/` or `assets/` file included; `inaccurate` a High `inaccurate-reference` gap; `escapes` a High `reference-escape` gap), each `incompletePatterns[]` entry as a Medium `integration-pattern` gap, and the §4 scripts/assets gap:

  ```bash
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from coherence --input "{run_dir}/coherence.json"
  uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coherence-check --from structure --input "{run_dir}/references.json"
  ```

Then write the records no script wrote, each in the Ledger Record Format of `{outputFormatsFile}`: the §2.5 findings, titled with their `naive-coherence:` text and with their Source at the cited call's `{file}:{line}`; and in both modes a §2b / §5b migration section finding (Case 1 and Case 3 are Medium `migration-section` gaps, a Low `migration-section` gap when the reviewer downgraded Case 3 with an inline justification, and Case 2 is an Info `migration-section` gap). The split-body rows of the Reference Consistency table are not recorded here: coverage-check §1b recorded them. Write them as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without.

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


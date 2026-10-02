---
nextStepFile: 'doc-drift.md'
# A docs-only skill reaches this step after step 5a, so it goes on to the
# report.
reportStepFile: 'report.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder, where the earlier steps saved the helpers'
# JSON; this step writes the findings and their classification beside it.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
severityClassifyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-severity-classify.py'
  - '{project-root}/src/shared/scripts/skf-severity-classify.py'
# Every HALT after the [C] of upstream-checkout.md closes the private tree with it.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# §3: this skill's renderer of the severity tables, from the skill root.
renderDriftTablesScript: 'scripts/render-drift-tables.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 (step 1c for a compose-mode stack, step 5a for a docs-only skill) by severity (CRITICAL/HIGH/MEDIUM/LOW), derive the overall drift score, and produce a categorized findings table with confidence-tier labels.

## Rules

- Only classify existing findings — do not discover new drift items or suggest remediation
- Build the findings from the JSON the earlier steps saved, never from the report's tables: the helper projects each saved source into one finding per item, with its type, file, line, confidence and detail, and fixes every category the source decides. Judgment is left for the categories a finding leaves open (`category_choices`) and the ambiguous names
- Mapping each type and category to a severity, reducing the set to the drift score and counting per level have one answer each: the helper does them with its rule table, which states the rules of the bundled `references/severity-rules.md` (`--rules` prints it), so the grades cannot change between runs
- The confidence tier (T1 / T1-low / T2) travels with each finding from Steps 03/04 unchanged: the helper never touches it
- A provenance label difference (step 3's **Provenance label differences (not drift)** table) is never a finding: do not classify it, count it or let it move the drift score
- `{docs_only_skill}` is the `docs_only_skill` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still takes the docs-only route

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (the [C] of `upstream-checkout.md`), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, and `"drift_score"` once §2 saved the classification, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Build the Findings File

**Resolve `{severityClassifyHelper}`** from `{severityClassifyProbeOrder}`; first existing path wins (SKILL.md On Activation checked that one exists).

Print the rule table once. It lists the only type and category pairs the helper grades, each with the rule it implements:

```bash
uv run {severityClassifyHelper} --rules --format markdown
```

Project the JSON the earlier steps saved into the findings file:

```bash
uv run {severityClassifyHelper} --from-diff "{auditDataFolder}/structural-diff.json" --file-drift "{auditDataFolder}/file-drift.json" --semantic "{auditDataFolder}/semantic-findings.json" -o "{auditDataFolder}/findings.json"
```

A compose-mode stack has no structural diff: step 1c saved its constituents' freshness instead, so its command projects that file alone:

```bash
uv run {severityClassifyHelper} --constituents "{auditDataFolder}/constituent-freshness.json" -o "{auditDataFolder}/findings.json"
```

A docs-only skill (`{docs_only_skill}`) has neither: step 5a saved its documents' comparison, so its command projects that file alone:

```bash
uv run {severityClassifyHelper} --doc-drift "{auditDataFolder}/doc-drift.json" -o "{auditDataFolder}/findings.json"
```

The helper writes one finding per item, with its `type`, `category`, `name`, `detail`, `file`, `line` and `confidence` (and `source_library` for a stack): each export the diff lists, each Script/Asset Drift file (step 3 §4b), each drifted or missing constituent (step 1c), each Semantic Drift row (step 4) and each changed document of a docs-only skill (step 5a). A stage that did not run saved no file (no `file_entries`, a tier without semantic diff): the helper skips that file, and its summary line's `sources` says which files it read. Exit 1 saved nothing: an `error` that starts `Cannot write output` is a failed write (§2), and any other names the file to fix before running the command again.

Then edit `{auditDataFolder}/findings.json`, keeping every field the helper wrote unless a rule below changes it:

1. **Open categories.** A finding with `category_choices` holds its first choice as `category`: replace it with the choice that names the change when another fits better. A removed export stays `export` unless it is an internal helper the skill's documented patterns reference (`internal_helper`); a changed signature takes the choice that names what changed (for example `required_parameter` for a new required parameter, `style` or `whitespace` for a reformatted one).
2. **Ambiguous names.** A finding with `ambiguous_name: true` (step 3's Ambiguous Names table) stays `removed` or `added`, unless you judge a removed and an added finding of one name to be one export that moved. Then record the move as the helper would: the added finding becomes `{type: "moved", category: "export", detail: "moved from {removed file:line} to {file:line}"}` without `ambiguous_name`, and the removed finding is deleted.

Keep one finding per item: a rollup belongs to the tables §3 renders, after classification.

### 2. Classify, Score, and Count (deterministic)

Classify the findings file:

```bash
uv run {severityClassifyHelper} "{auditDataFolder}/findings.json" -o "{auditDataFolder}/severity.json"
```

- **Exit 0:** the helper saved the result and printed one line with `drift_score`, `total_findings`, `total_items` and `by_severity`.
- **Exit 1 with `problems[]`:** some findings fit no rule. Each problem names the finding (its `index` in the findings file), its `type` and `category`, and why. Re-categorize exactly those findings (a pair from the rule table, a category from the finding's `category_choices`, an ambiguous finding back to `removed` or `added`), then run the command again.
- **Exit 1 without `problems[]`:** nothing was saved. An `error` that starts `Cannot write output` (here or in §1) is a failed write: HALT with **exit 4**, `halt_reason: "write-failed"`, phase `severity-classify:save`, `"path": "{auditDataFolder}"`. Any other `error` names a findings file the helper could not read: fix it, then run the command again.
- **Exit 2:** a usage error in the command itself.

The saved result, CRITICAL first:

```json
{
  "status": "ok",
  "drift_score": "CLEAN|MINOR|SIGNIFICANT|CRITICAL",
  "total_findings": N,
  "total_items": N,
  "added_export_count": N,
  "by_severity": {"CRITICAL": N, "HIGH": N, "MEDIUM": N, "LOW": N},
  "findings": [ {"type": "...", "category": "...", "name": "...", "detail": "...", "file": "...", "line": N, "confidence": "...", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "rule": "..."} ]
}
```

Consume `drift_score`, `by_severity`, the totals and each finding's `severity` directly: do not recount or recompute the score in prose. `total_findings` counts the findings (the rows), and `by_severity` sums to `total_items`.

### 3. Compile Severity Classification Section

Render the section from the saved classification, never by hand. `{renderDriftTablesScript}` resolves relative to the skill root; from `{project-root}`, run:

```bash
uv run {renderDriftTablesScript} severity "{auditDataFolder}/severity.json"
```

It prints the section's tables (`--help` lists them). A rollup changes no count: the headings and the summary come from the JSON.

Append to {outputFile}:

```markdown
## Severity Classification

{what the command printed, unchanged}
```

When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not read: write `Severity tables not rendered: {error}` in place of its output and go on, since §4 and step 6 read the saved classification, not these tables.

### 4. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'severity-classify'` to `stepsCompleted`
- Set `drift_score` to `{drift_score}` from the helper

Once the ## Severity Classification section has been appended with all findings classified, load, read fully, and execute `{nextStepFile}` (documentation drift), or `{reportStepFile}` for a docs-only skill (`{docs_only_skill}`), whose step 5a already ran.

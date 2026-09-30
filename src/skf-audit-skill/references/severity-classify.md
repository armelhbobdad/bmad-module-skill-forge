---
nextStepFile: 'step-doc-drift.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
severityRulesFile: '{severityRulesPath}'
# This run's stage data folder, where the earlier steps saved the helpers'
# JSON; this step writes the findings and their classification beside it.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
severityClassifyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-severity-classify.py'
  - '{project-root}/src/shared/scripts/skf-severity-classify.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 (or step 1c for a compose-mode stack) by severity (CRITICAL/HIGH/MEDIUM/LOW), derive the overall drift score, and produce a categorized findings table with confidence-tier labels.

## Rules

- Only classify existing findings — do not discover new drift items or suggest remediation
- Build the findings from the JSON the earlier steps saved, never from the report's tables: the helper projects each saved source into one finding per item, with its type, file, line, confidence and detail, and fixes every category the source decides. Judgment is left for the categories a finding leaves open (`category_choices`) and the ambiguous names
- Mapping each type and category to a severity, reducing the set to the drift score and counting per level have one answer each: the helper does them with its rule table, which states the rules of the bundled `references/severity-rules.md` (`--rules` prints it), so the grades cannot change between runs
- The confidence tier (T1 / T1-low / T2) travels with each finding from Steps 03/04 unchanged: the helper never touches it
- A provenance label difference (step 3's **Provenance label differences (not drift)** table) is never a finding: do not classify it, count it or let it move the drift score

## MANDATORY SEQUENCE

### 1. Build the Findings File

**Resolve `{severityClassifyHelper}`** from `{severityClassifyProbeOrder}`; first existing path wins.

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

The helper writes one finding per item, with its `type`, `category`, `name`, `detail`, `file`, `line` and `confidence` (and `source_library` for a stack): each export the diff lists, each Script/Asset Drift file (step 3 §4b), each drifted or missing constituent (step 1c) and each Semantic Drift row (step 4). A stage that did not run saved no file (no `file_entries`, a tier without semantic diff): the helper skips that file, and its summary line's `sources` says which files it read. Exit 1 saved nothing: an `error` that starts `Cannot write output` is a failed write (§2), and any other names the file to fix before running the command again.

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
- **Exit 1 without `problems[]`:** nothing was saved. An `error` that starts `Cannot write output` (here or in §1) is a failed write: HALT with **exit 4**, `halt_reason: "write-failed"`, and when `{headless_mode}` emit the error envelope on **stderr** (shape per SKILL.md → Result Contract). Any other `error` names a findings file the helper could not read: fix it, then run the command again.
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

**If `uv`/the helper cannot execute** (e.g. claude.ai web): classify in the main thread. Build the findings the helper would from the saved JSON (or, when step 3 fell back too, from its tables, one finding per export): `added`, `removed` or `moved` with category `export` for each export the diff lists, `changed`/`location` for a line-only change and the category that names any other change, `added`, `removed` or `changed` with category `file` for each Script/Asset file, `changed`/`constituent` for a drifted constituent and `removed`/`constituent` for a missing one, and the Semantic Drift rows as step 4 saved them. Grade each type and category pair by the line of {severityRulesFile} that states it, reduce with its Overall Drift Score table (CLEAN = no findings; MINOR = LOW only; SIGNIFICANT = any MEDIUM/HIGH, no CRITICAL; CRITICAL = any CRITICAL present), and save the result over `{auditDataFolder}/severity.json` in the helper's shape (`status: "ok"`, `drift_score`, `total_findings`, `total_items`, `added_export_count`, `by_severity`, and `findings[]` each with its `severity` and `rule`), so §3 and step 6 read it as they would the helper's.

### 3. Compile Severity Classification Section

**Rollup when rendering.** A severity table may collapse ≥ 10 of its findings that share one root cause (deleted source file, renamed module, entire package tree removed) into one row, as step 3 §5 does for its tables. Keep the 6-column severity table shape; the rollup encodes root cause, count, and representative symbols **inline in the `Finding` cell** rather than adding columns, so rollup and per-item rows render cleanly in one table. Changed-signature and cross-file findings remain per-row; they were not eligible for rollup in step 3 and are not eligible here. A rollup changes no count: the headings and the summary come from the helper.

**Rollup row form (any severity table):**

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| N | {root cause} (×{Count}; rep: `{sym1}`, `{sym2}`, `{sym3}`, …) | {structural/semantic} | {shared detail} | {root-cause path} | {T1/T1-low/T2} |

Append to {outputFile}, one row per finding of `{auditDataFolder}/severity.json` (or per rollup), filling the counts from `by_severity`. A finding with no `confidence` (a hash comparison) shows `n/a`, and every finding but a `semantic` one is structural:

```markdown
## Severity Classification

**Overall Drift Score: {drift_score}**

### CRITICAL ({by_severity.CRITICAL})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T1-low/T2} |

### HIGH ({by_severity.HIGH})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T1-low/T2} |

### MEDIUM ({by_severity.MEDIUM})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T1-low/T2} |

### LOW ({by_severity.LOW})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T1-low/T2} |

### Classification Summary

| Severity | Count |
|----------|-------|
| CRITICAL | {by_severity.CRITICAL} |
| HIGH | {by_severity.HIGH} |
| MEDIUM | {by_severity.MEDIUM} |
| LOW | {by_severity.LOW} |
| **Total** | {total_items} |
```

### 4. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'severity-classify'` to `stepsCompleted`
- Set `drift_score` to `{drift_score}` from the helper

Once the ## Severity Classification section has been appended with all findings classified, load, read fully, and execute `{nextStepFile}` (documentation drift).

# Output Section Formats

## Coherence Analysis — Naive Mode

```markdown
## Coherence Analysis

**Mode:** Naive (structural validation only)
**Coherence category:** Not scored (weight redistributed)
**Migration Section:** {the note migration-section-rules.md Case 4 records; leave this line out when it records none}

### Structural Findings

| # | Type | Severity | Detail | Line |
|---|------|----------|--------|------|
| {per-issue rows} |

**Structural Issues:** {count}
```

## Coherence Analysis — Naive Mode: Reference Consistency (split-body)

Only rendered when `references/` directory exists alongside SKILL.md. Each row is a split-body gap coverage-check recorded. **Other Side** is the other file of its pair, at its line: `SKILL.md:{skill_md_line}`, or `{other_file}:{other_line}` for two references. Its Source is at **Other Side** when the pinned source contradicts that side and agrees with **Reference File**, else at `{Reference File}:{Reference Line}`. **Contradicted Side** is the path of the one file the source contradicts (`SKILL.md` or a `references/` file's path), `none` when both forms agree with it, or `not settled` when it contradicts both or no source settled it. **Exports Cross-Checked** is `crossChecked.count` from `{run_dir}/inventory.json`, which `scripts/validate-inventory.py` writes: the inventory's names that two or more of the files it reads write, never counted by hand.

```markdown
### Reference Consistency (split-body)

| # | Reference File | Export | Issue | Other Side | Reference Line | Contradicted Side |
|---|---------------|--------|-------|------------|---------------|-------------------|
| {per-mismatch rows} |

**Exports Cross-Checked:** {crossChecked.count}
**Mismatches Found:** {count}
```

## Coherence Analysis — Contextual Mode

```markdown
## Coherence Analysis

**Mode:** Contextual (full reference validation)
**References Found:** {count}
**References Valid:** {count}
**Broken References:** {count}
**Migration Section:** {the note migration-section-rules.md Case 4 records; leave this line out when it records none}

### Reference Validation

| Reference | Type | Line | Target Exists | Accurate | Severity | Issues |
|-----------|------|------|--------------|----------|----------|--------|
| {per-reference rows} |

### Integration Pattern Completeness

| Pattern | Complete | Issue |
|---------|----------|-------|
| {per-pattern rows} |

### Coherence Score

- **Reference Validity:** {valid}/{total} ({percentage}%)
- **Integration Completeness:** {complete}/{total} ({percentage}%)
- **Combined Coherence:** {percentage}%
```

## Ledger Record Format

Every gap a stage finds is one JSON record in the run's gap ledger, `{forge_version}/test-findings-{run_id}.json`, appended through `scripts/gap-ledger.py append`; no stage writes gap entries into the report by hand:

```json
{
  "severity": "Critical | High | Medium | Low | Info",
  "category": "the category of its Gap Severity table row, such as missing-export",
  "title": "one line",
  "source": "file:line, or a section reference when no line applies",
  "remediation": "the exact action that fixes the gap",
  "issue": "what is wrong (optional)",
  "export": "the export the gap is about (optional; set it whenever the gap is about one export)"
}
```

- `severity` and `category` come from one row of the Gap Severity table in `references/scoring-rules.md`. The script refuses a category outside its vocabulary, which `uv run scripts/gap-ledger.py categories` lists.
- `source` is a `file:line` pair whenever a line applies, with nothing after it: update-skill reads the pair as the gap's citation. A gap inside the skill package cites `SKILL.md:{line}` or `references/{file}.md:{line}`. A split-body record, titled `Split-body mismatch: {export} ({reference_file})`, or `Split-body mismatch: {export} ({other_file}, {reference_file})` for two references, cites the side the pinned source contradicts: the other side, `SKILL.md:{skill_md_line}` or `{other_file}:{other_line}`, when `{reference_file}` agrees with the source declaration and the other side does not, else `{reference_file}:{reference_line}`, also when no source settled it. Its remediation names the file to edit and the file and line whose form it takes, or, when each form agrees with a different declaration of the name, the citation to add beside each, and update-skill changes only what it names as contradicting.
- `remediation` follows the Remediation Quality Rules below and names each file it touches.
- Leave out `id`, `group` and `stage`: the script assigns them (`GAP-{NNN}` in the order the gaps were recorded, the group from the category, the stage from `--stage`).

## Gap Report

`uv run scripts/gap-ledger.py render --ledger <ledger> --heading` prints the Gap Report, its effort column included, and report.md §4c writes it unchanged: it is never written by hand.

## Discovery Quality Subsection

Written under the Gap Report by report.md §4c:

```markdown
### Discovery Quality

**Discovery Test:** {PASS (3/3) | WARN (2/3) | FAIL ({N}/3 misrouted) | skipped: {reason} | not run: the hard gate blocked the run}

| # | Prompt | Selected Skill | Result |
|---|--------|----------------|--------|
| {per-prompt rows, when the test ran} |

{description optimization hints from report.md §4b.4, when any}
```

## Remediation Quality Rules

- **Good:** "Add documentation for `formatDate(date: Date, format?: string): string` exported from `src/utils.ts:42`. Include the optional `format` parameter with default value `'YYYY-MM-DD'`."
- **Bad:** "Document the missing function."
- **Good:** "Update signature in SKILL.md line 78 from `(date: Date) => string` to `(date: Date, format?: string) => string` to match source at `src/utils.ts:42`."
- **Bad:** "Fix the signature mismatch."

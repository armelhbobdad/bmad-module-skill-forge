---
nextStepFile: 'step-11-maintenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
gateScript: 'scripts/campaign-quality-gate.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Export

## STEP GOAL:

Classify every completed skill against the quality gate, present the verdicts for operator review, and gate the export of the skills that clear it behind explicit confirmation. This is the only campaign stage whose gate holds back a file write: nothing is exported until the operator confirms.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `9`.
- If `{headless_mode}` is true, auto-proceed past the write-gate with `[E]` and log: "headless: auto-proceed past export write-gate".

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Directive

If `campaign.directive_path` is set in state, the gate script applies its `## Quality Overrides` itself (§3), so do not adjust the gate by hand. Read any other section as campaign-wide context, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3 — Collect Export Candidates

Classify every completed skill against its quality gate, passing `--directive-file` when state sets `campaign.directive_path`; never compare scores by hand:

```
uv run {gateScript} classify --state-file {stateFile} [--directive-file <campaign.directive_path>]
```

Each completed skill gets a `verdict`: `pass` (score at or above its `soft_target`), `fallback` (at or above its `soft_fallback`) or `fail` (below the fallback, or no score). Only `pass` and `fallback` skills are export candidates (`export[]`); `excluded[]` lists the others with their `reason`, and they stay on disk and in the report. A Tier B score is the skill-check score QS records, not a test-skill score. Log each `excluded[]` skill and each `unparsed` or `warnings` entry to the decision log. On exit 2 (an override that breaks the gate, or a directive that cannot be read), HALT (exit code 2, `invalid-input`) with its `error`.

If `export[]` is empty (no completed skill, or none clears the gate), display a warning naming any `excluded[]` skills and proceed directly to §6 (stage completion): there is nothing to export.

Present the verdicts, one row per entry of its `skills[]`:

| # | Name | Tier | Quality Score | Gate | Skill Path |
|---|------|------|---------------|------|------------|
| 1 | {name} | {tier} | {quality_score} | {verdict} | {skill_path} |
| ... | ... | ... | ... | ... | ... |

When `excluded[]` is not empty, list it under the table: "**Not exported (below the quality gate):** {name} ({quality_score}: {reason}), ..."

Display: "**{N} skill(s) ready for export.**" ({N} is the number of `export[]` skills.)

### §4 — Write-Gate HALT

Present the export confirmation gate:

"**Export Gate — Confirm before writing files**

{N} skill(s) that clear the quality gate will be exported via `skf-export-skill`:

{summary table and exclusions from §3}

- **[E]xport all**: invoke `skf-export-skill` for each skill in `export[]`
- **[C]ancel**: halt the campaign gracefully (no files written, resume later)

Choose [E] or [C]:"

**HALT and wait for operator input.**

**Headless mode:** auto-proceed with `[E]` and log: "headless: auto-proceed past export write-gate". `[E]` exports only the `export[]` skills; the excluded ones are logged at §3.

#### On `[C]ancel`:

Display: "Export cancelled by operator. Campaign halted gracefully — no files written. Resume later to retry export."

Log the cancellation to the decision log, then HALT with exit code 11 (`export-cancelled`). Do NOT mark the campaign as failed — this is a graceful, resumable halt; the operator may resume later.

#### On `[E]xport`:

Log the export decision to the decision log, then proceed to §5.

### §5 — Invoke EX

For each skill in `export[]` (from §3), invoke `skf-export-skill` in headless mode:

```
skf-export-skill {skill_name} --headless
```

Capture the result envelope `SKF_EXPORT_RESULT_JSON` per skill.

**On per-skill EX success** (exit code 0): log the result and continue.

**On per-skill EX failure** (non-zero exit): log the error (exit code, envelope if available, or stderr). Continue with remaining skills — per-skill failure does not block remaining exports.

After all exports complete, display a summary:

"**Export Results:**
- Exported: {success_count} skill(s)
- Failed: {fail_count} skill(s)
- Not exported, below the quality gate: {excluded_count} skill(s)
{list of failed skills if any}"

### §6 — Stage Completion

Set `campaign.current_stage` to `9`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display export summary: skills exported count, failures count (if any), and per-skill results. Chain to `{nextStepFile}`.

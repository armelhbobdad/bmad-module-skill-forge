---
nextStepFile: 'step-11-maintenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
gateScript: 'scripts/campaign-quality-gate.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Export

## STEP GOAL:

Classify every completed skill against the quality gate, present the verdicts for operator review, and gate the export of the skills that clear it behind explicit confirmation. This is the only campaign stage whose gate holds back a file write: nothing is exported until the operator confirms.

## RULES

- Write `campaign.current_stage` = 9 only in this stage's final state write (§6), after the export gate: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work, and a campaign cancelled at the gate shows the gate again when it resumes.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, auto-proceed past the write-gate with `[E]` and log "headless: auto-proceed past export write-gate" (type `auto`); emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Directive

If `campaign.directive_path` is set in state, the gate script applies its `## Quality Overrides` itself (§3), so do not adjust the gate by hand. Read any other section as campaign-wide context, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3: Collect Export Candidates

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

### §4: Write-Gate HALT

Present the export confirmation gate:

"**Export Gate — Confirm before writing files**

{N} skill(s) that clear the quality gate will be exported via `skf-export-skill`:

{summary table and exclusions from §3}

- **[E]xport all**: invoke `skf-export-skill` for each skill in `export[]`
- **[C]ancel**: halt the campaign gracefully (no files written, resume later)

Choose [E] or [C]:"

**HALT and wait for operator input.**

**Headless mode:** auto-proceed with `[E]` (the RULES log line). `[E]` exports only the `export[]` skills; the excluded ones are logged at §3.

#### On `[C]ancel`:

Display: "Export cancelled by operator. Campaign halted gracefully — no files written. Resume later to retry export."

Log the cancellation (type `decision`), then HALT with exit code 11 (`export-cancelled`). Do NOT mark the campaign as failed: this is a graceful, resumable halt, and nothing of this stage is written, so the operator may resume later at this gate.

#### On `[E]xport`:

Log the export decision (type `decision`), then proceed to §5.

### §5: Invoke EX

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

### §6: Stage Completion

Write the stage:

```
uv run {stateScript} set-stage --state-file {stateFile} --stage 9
```

## OUTPUT

Display export summary: skills exported count, failures count (if any), and per-skill results. Chain to `{nextStepFile}`.

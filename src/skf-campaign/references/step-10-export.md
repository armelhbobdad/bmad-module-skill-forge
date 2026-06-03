---
nextStepFile: 'step-11-maintenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Export

## STEP GOAL:

Present all completed skills for operator review and gate the export behind explicit confirmation. This is the only campaign step that requires manual approval before proceeding — no files are written until the operator confirms.

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

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3 — Collect Export Candidates

Gather all skills from `skills[]` with `status == "completed"`. These are the export candidates.

If no completed skills exist, display a warning and proceed directly to §6 (stage completion) — there is nothing to export.

Present a summary table of export candidates:

| # | Name | Tier | Quality Score | Skill Path |
|---|------|------|---------------|------------|
| 1 | {name} | {tier} | {quality_score} | {skill_path} |
| ... | ... | ... | ... | ... |

Display: "**{N} skill(s) ready for export.**"

### §4 — Write-Gate HALT

Present the export confirmation gate:

"**Export Gate — Confirm before writing files**

{N} completed skill(s) will be exported via `skf-export-skill`:

{summary table from §3}

- **[E]xport all** — invoke `skf-export-skill` for each completed skill
- **[C]ancel** — halt the campaign gracefully (no files written, resume later)

Choose [E] or [C]:"

**HALT and wait for operator input.**

**Headless mode:** auto-proceed with `[E]` and log: "headless: auto-proceed past export write-gate".

#### On `[C]ancel`:

Display: "Export cancelled by operator. Campaign halted gracefully — no files written. Resume later to retry export."

Log the cancellation to the decision log, then HALT with exit code 11 (`export-cancelled`). Do NOT mark the campaign as failed — this is a graceful, resumable halt; the operator may resume later.

#### On `[E]xport`:

Log the export decision to the decision log, then proceed to §5.

### §5 — Invoke EX

For each completed skill (from §3), invoke `skf-export-skill` in headless mode:

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
{list of failed skills if any}"

### §6 — Stage Completion

Set `campaign.current_stage` to `9`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display export summary: skills exported count, failures count (if any), and per-skill results. Chain to `{nextStepFile}`.

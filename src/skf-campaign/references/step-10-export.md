---
nextStepFile: 'step-11-maintenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
---

<!-- Config: communicate in {communication_language}. -->

# Export

## STEP GOAL:

Present all completed skills for operator review and gate the export behind explicit confirmation. This is the only campaign step that requires manual approval before proceeding — no files are written until the operator confirms.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- Update `campaign.current_stage` to `9`.
- If `{headless_mode}` is true, auto-proceed past the write-gate with `[E]` and log: "headless: auto-proceed past export write-gate".

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Collect Export Candidates

Gather all skills from `skills[]` with `status == "completed"`. These are the export candidates.

If no completed skills exist, display a warning and proceed directly to §5 (stage completion) — there is nothing to export.

Present a summary table of export candidates:

| # | Name | Tier | Quality Score | Skill Path |
|---|------|------|---------------|------------|
| 1 | {name} | {tier} | {quality_score} | {skill_path} |
| ... | ... | ... | ... | ... |

Display: "**{N} skill(s) ready for export.**"

### §3 — Write-Gate HALT

Present the export confirmation gate:

"**Export Gate — Confirm before writing files**

{N} completed skill(s) will be exported via `skf-export-skill`:

{summary table from §2}

- **[E]xport all** — invoke `skf-export-skill` for each completed skill
- **[C]ancel** — halt the campaign gracefully (no files written, resume later)

Choose [E] or [C]:"

**HALT and wait for operator input.**

**Headless mode:** auto-proceed with `[E]` and log: "headless: auto-proceed past export write-gate".

#### On `[C]ancel`:

Display: "Export cancelled by operator. Campaign halted gracefully — no files written. Resume later to retry export."

HALT the campaign. Do NOT mark the campaign as failed — the operator may resume later.

#### On `[E]xport`:

Proceed to §4.

### §4 — Invoke EX

For each completed skill (from §2), invoke `skf-export-skill` in headless mode:

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

### §5 — Stage Completion

Set `campaign.current_stage` to `9`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display export summary: skills exported count, failures count (if any), and per-skill results. Chain to `{nextStepFile}`.

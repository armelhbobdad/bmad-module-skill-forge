---
nextStepFile: 'step-08-verify.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Capstone

## STEP GOAL:

Compose a capstone stack skill from all completed individual skills using SS compose-mode. The capstone represents the final integrated view of all campaign skills — a single stack skill that documents how the constituent libraries connect.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `6`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. SS compose-mode supports headless.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Collect Completed Skills

Gather all skills from `skills[]` with `status == "completed"` — this includes both Tier A skills (processed in step-05) and Tier B skills (processed in step-06). Extract their `skill_path` values.

If no completed skills exist, do NOT HALT — a campaign where everything failed is exactly when the operator most needs the downstream diagnostic report. Set `campaign.capstone` to `null`, warn ("No completed skills — skipping capstone composition; verification and the campaign report will still run so failures are explained"), log the skip to the decision log, and skip directly to §5 (Stage Completion) so the chain continues to verify → … → the report. step-10 (export) and step-11 (report) already handle the zero-completed case.

### §3 — Invoke SS Compose-Mode

Invoke `skf-create-stack-skill` in compose-mode with:

- The collected `skill_path` values as input skills
- `campaign.name` as the stack identifier

Capture the result: stack skill path and quality score from the SS result output (`SKF_STACK_RESULT_JSON`).

### §4 — Record Capstone Results

Persist the capstone outcome to `campaign.capstone` in the state (campaign-level summary; the composed skill itself lives at `skill_path`):

- `campaign.capstone.skill_path` — stack skill path (from SS result)
- `campaign.capstone.quality_score` — quality score (from SS result)
- `campaign.capstone.verified` — `null` for now; set by the verify stage (step-08) once the stack is checked
- `campaign.capstone.completed_at` — current ISO-8601 with timezone

The capstone is a derived artifact — it is **not** tracked as a skill entry in the `skills[]` array. Its campaign-level summary lives in `campaign.capstone`; the constituent skill list and any verbose detail are reported in the step output and are available to downstream steps (verify, refine).

### §5 — Stage Completion

Set `campaign.current_stage` to `6`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state (including `campaign.capstone` from §4).

## OUTPUT

Display capstone summary: stack skill name, path, quality score, and the list of constituent skills. Chain to `{nextStepFile}`.

---
nextStepFile: 'step-08-verify.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
gateScript: 'scripts/campaign-quality-gate.py'
manifestScript: 'scripts/campaign-parse-manifest.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Capstone

## STEP GOAL:

Compose a capstone stack skill from the completed individual skills that clear the quality gate, using SS compose-mode. The capstone represents the final integrated view of the campaign's exported skills: a single stack skill that documents how the constituent libraries connect.

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

Classify the completed skills (Tier A from step-05, Tier B from step-06) against the quality gate as Export will, passing `--directive-file` when state sets `campaign.directive_path`; never compare scores by hand:

```
uv run {gateScript} classify --state-file {stateFile} [--directive-file <campaign.directive_path>]
```

The capstone composes the skills in its `export[]` (the `pass` and `fallback` verdicts), so it never describes a skill the gate keeps from export: log each `excluded[]` skill as "capstone: {name} left out, below the quality gate ({reason})". Name each composed skill by its row in `skills[]`: its `skill_path` when the row has one (the package its build wrote, which for a Tier B skill quick-skill names after the library, not the campaign target), else its `name`. On exit 2 (an override that breaks the gate, or a directive that cannot be read), HALT (exit code 2, `invalid-input`) with its `error`.

If `export[]` is empty (no completed skill, or none clears the gate), do NOT HALT: a campaign where everything failed is exactly when the operator most needs the downstream diagnostic report. Set `campaign.capstone` to `null`, warn ("No skill clears the quality gate: skipping capstone composition; verification and the campaign report will still run so failures are explained"), log the skip to the decision log, and skip directly to §5 (Stage Completion) so the chain continues to verify → … → the report. step-10 (export) and step-11 (report) already handle the zero-completed case.

### §3 — Invoke SS Compose-Mode

Invoke `skf-create-stack-skill` with `--headless` and these inputs, so it asks nothing and prints its result envelope:

- `mode`: `compose`
- `skills`: the §2 paths and names, comma-separated (compose mode takes them as its constituent skills)
- `stack_name`: the `stack_name` that `uv run {manifestScript} --stack-name {stateFile}` prints, the campaign name as a skill name cut to leave room for the `-stack` SS appends; when it prints null, leave the input out and SS names the stack `{project_name}-stack`
- `architecture_doc_path`: `campaign.architecture_doc_path`, only when state sets it

Read its `SKF_STACK_RESULT_JSON` line. On `status` `success`, keep its `skill_package` (the stack skill's path) and `quality_score` (the skill-check score SS records, null when skill-check did not run; it is not a test-skill score). On `status` `error`, or no envelope, log its `halt_reason` (or "no result envelope") to the decision log, set `campaign.capstone` to `null` and skip to §5: verification and the campaign report still run.

### §4 — Record Capstone Results

Persist the capstone outcome to `campaign.capstone` in the state (campaign-level summary; the composed skill itself lives at `skill_path`):

- `campaign.capstone.skill_path`: `skill_package` from the SS envelope
- `campaign.capstone.quality_score`: `quality_score` from the SS envelope
- `campaign.capstone.verified`: `null` for now; set by the verify stage (step-08) once the stack is checked
- `campaign.capstone.completed_at`: current ISO-8601 with timezone

The capstone is a derived artifact — it is **not** tracked as a skill entry in the `skills[]` array. Its campaign-level summary lives in `campaign.capstone`; the constituent skill list and any verbose detail are reported in the step output and are available to downstream steps (verify, refine).

### §5 — Stage Completion

Set `campaign.current_stage` to `6`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state (including `campaign.capstone` from §4).

## OUTPUT

Display capstone summary: stack skill name, path, quality score, and the list of constituent skills. Chain to `{nextStepFile}`.

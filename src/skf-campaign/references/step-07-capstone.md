---
nextStepFile: 'step-08-verify.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
gateScript: 'scripts/campaign-quality-gate.py'
manifestScript: 'scripts/campaign-parse-manifest.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Capstone

## STEP GOAL:

Compose a capstone stack skill from the completed individual skills that clear the quality gate, using SS compose-mode. The capstone represents the final integrated view of the campaign's exported skills: a single stack skill that documents how the constituent libraries connect.

## RULES

- Write `campaign.current_stage` = 6 only in this stage's final state write (§4), after the capstone is recorded: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. SS compose-mode runs headless.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Collect Completed Skills

Classify the completed skills (Tier A from step-05, Tier B from step-06) against the quality gate as Export will, passing `--directive-file` when state sets `campaign.directive_path`; never compare scores by hand:

```
uv run {gateScript} classify --state-file {stateFile} [--directive-file <campaign.directive_path>]
```

The capstone composes the skills in its `export[]` (the `pass` and `fallback` verdicts), so it never describes a skill the gate keeps from export: log each `excluded[]` skill as "capstone: {name} left out, below the quality gate ({reason})". Name each composed skill by the `export_name` of its row in `skills[]` (the skill folder its build wrote), as Export does. On exit 2 (an override that breaks the gate, or a directive that cannot be read), HALT (exit code 2, `invalid-input`) with its `error`.

If `export[]` is empty (no completed skill, or none clears the gate), do NOT HALT: a campaign where everything failed is exactly when the operator most needs the downstream diagnostic report. Warn ("No skill clears the quality gate: skipping capstone composition; verification and the campaign report will still run so failures are explained"), log the skip (type `event`), and go to §4 with no capstone, so the chain continues to verify, refine, export and the report. step-10 (export) and step-11 (report) already handle the zero-completed case.

### §3: Invoke SS Compose-Mode

Invoke `skf-create-stack-skill` with `--headless` and these inputs, so it asks nothing and prints its result envelope:

- `mode`: `compose`
- `skills`: the §2 `export_name` values, comma-separated (compose mode takes them as its constituent skill folders)
- `stack_name`: the `stack_name` that `uv run {manifestScript} --stack-name {stateFile}` prints, the campaign name as a skill name cut to leave room for the `-stack` SS appends; when it prints null, leave the input out and SS names the stack `{project_name}-stack`
- `architecture_doc_path`: `campaign.architecture_doc_path`, only when state sets it

Keep the `SKF_STACK_RESULT_JSON` line it prints for §4, which records it. On `status` `error`, or no envelope, log its `halt_reason` (or "no result envelope", type `event`): verification and the campaign report still run.

### §4: Record the Capstone and Complete the Stage

Record the capstone outcome and the stage in one write, passing the §3 envelope line to the helper, which reads it (never copy its fields by hand):

```
uv run {stateScript} set-campaign --state-file {stateFile} --capstone - --stage 6 <<'SKF_RESULT'
<the SKF_STACK_RESULT_JSON line SS printed>
SKF_RESULT
```

From a `success` envelope it sets `campaign.capstone`, the campaign-level summary (the composed skill itself lives at `skill_path`):

- `campaign.capstone.skill_path`: `skill_package` from the SS envelope
- `campaign.capstone.quality_score`: `quality_score` from the SS envelope (the skill-check score SS records, null when skill-check did not run; it is not a test-skill score)
- `campaign.capstone.verified`: `null` for now; set by the verify stage (step-08) once the stack is checked
- `campaign.capstone.completed_at`: the time of the write, from the clock

An `error` envelope sets `campaign.capstone` to `null` (the helper names it in `not_recorded`). When §2 found no skill to compose, or SS printed no envelope, record no capstone instead: `uv run {stateScript} set-campaign --state-file {stateFile} --no-capstone --stage 6`.

The capstone is a derived artifact: it is **not** tracked as a skill entry in the `skills[]` array. The constituent skill list and any verbose detail are reported in the step output and are available to downstream steps (verify, refine).

## OUTPUT

Display capstone summary: stack skill name, path, quality score, and the list of constituent skills. Chain to `{nextStepFile}`.

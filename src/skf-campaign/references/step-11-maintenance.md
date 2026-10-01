---
nextStepFile: 'health-check.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
reportFile: '{campaignWorkspacePath}/campaign-report.md'
resultContextFile: '{campaignWorkspacePath}/_result-context.json'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
reportScript: 'scripts/campaign-report.py'
reportTemplate: '{reportTemplatePath}'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Maintenance

## STEP GOAL:

Generate the campaign report from the accumulated state, record the campaign as finished, run the `on_complete` hook, build the headless result envelope, and chain to the health check, the campaign's terminal step.

## RULES

- Write `campaign.current_stage` = 10 only in this stage's final state write (§3), after the report: step-resume resumes at `current_stage + 1`, capped at 10, so a report step cut short before §3 runs again. After §3 a resume reports the campaign complete and, in headless mode, prints its envelope again from `{resultContextFile}`; it does not run the §4 hook.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. The success envelope is built in §5 and displayed by the health check as the run's last line, never here.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Generate Campaign Report

Invoke the campaign report script:

```
uv run {reportScript} \
    --state-file {stateFile} \
    --template-file {reportTemplate} \
    --output-file {reportFile} \
    --context-file {resultContextFile} \
    --decision-log {decisionLogFile}
```

Its JSON result on stdout carries `skills_completed`, `skills_failed`, `quality_scores`, `export_verdicts` (each completed skill's quality-gate verdict at Export), `skills_excluded` (the completed skills the gate kept from export) and `duration`, already computed: §6 displays them, and §5 builds the envelope from `{resultContextFile}`, the payload the script also writes, on success and on failure alike.

**On success** (exit code 0): log the report path and the summary stats from the result JSON (type `event`).

**On failure** (exit code 2): the campaign itself has already completed, so do NOT discard it over a missing summary artifact. Display the error from stderr and log "report generation failed (degraded): {error}" (type `event`), then CONTINUE to §3. The payload the script wrote in its place is the degraded finish (`status` `error`, `halt_reason` `report-failure`, exit code 10, no report path), a signal in the envelope and never a hard halt that throws away a finished campaign.

### §3: Record the Finished Campaign

```
uv run {stateScript} set-stage --state-file {stateFile} --stage 10
```

On exit 3, HALT (exit code 3, `invalid-state`) with its `errors[]`.

### §4: Post-Completion Hook

Skip this section when `{onComplete}` (resolved in On Activation) is empty. Otherwise run it now, after the final state write, so a hook that archives or commits the workspace captures the finished campaign. When §2 wrote the report, run `{onComplete} --report-path={reportFile}`; when §2 degraded, run `{onComplete}` without `--report-path`, since there is no report to read. Log the outcome (type `event`): a hook failure is recorded but never fails the campaign.

### §5: Result Envelope

When `{headless_mode}` is true, build the campaign's result envelope from the payload §2 wrote:

```
uv run {emitEnvelopeHelper} emit --workflow skf-campaign < {resultContextFile}
```

`{emitEnvelopeHelper}` is the shared emitter (its path is in the Result Contract of `references/campaign-contracts.md`). It checks the line against `shared/scripts/schemas/skf-campaign-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development), the one definition of the envelope: the success line, or the degraded one when §2 failed. Bind `{result_envelope_line}` to the `SKF_CAMPAIGN_RESULT_JSON:` line it prints, and do not display it here: the health check displays it verbatim as the run's last line, the final message a `claude -p` caller reads. If `{resultContextFile}` is missing (the report script could not write it), give the same command `{"status": "error", "halt_reason": "report-failure", "decision_log": "{decisionLogFile}"}` on stdin instead. If the emitter exits non-zero, log its error (type `event`) and leave `{result_envelope_line}` empty.

When not in headless mode, skip this section.

### §6: Chain to Health Check

When `{headless_mode}` is false, display, from the §2 result: "**Campaign complete.** {skills_completed} completed, {skills_failed} failed in {duration}. Report at `{reportFile}`." When §2 degraded, display "**Campaign finished, but the report could not be generated** (see the decision log); state is intact." instead. In headless mode display nothing: the envelope is the run's last line.

Chain to `{nextStepFile}`: the health-check step is the true terminal step, so do not stop here even though the summary reads as final.

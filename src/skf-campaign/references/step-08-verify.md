---
nextStepFile: 'step-09-refine.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Verify

## STEP GOAL:

Invoke VS (skf-verify-stack) in headless mode against all completed campaign skills to produce a feasibility report. The report cross-references generated skills against the project's architecture document, providing coverage analysis and integration verdicts for operator review.

## RULES

- Write `campaign.current_stage` = 7 only in this stage's final state write (§5), after the verification is recorded: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. VS runs headless with `--headless`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3: Locate Architecture Doc

Resolve the architecture document path, preferring the value persisted in state:

1. If `campaign.architecture_doc_path` is set in state and the file exists, use it directly.
2. Otherwise discover it: check `{project-root}/docs/architecture.md` (SKF convention), then `{project-root}/_bmad-output/planning-artifacts/architecture.md` (BMM convention).
3. If still not found and `{headless_mode}` is false: prompt the operator to provide the architecture doc path.
4. If still not found and `{headless_mode}` is true: skip VS invocation with a warning; do not HALT. Log that verification was skipped due to missing architecture doc (type `event`) and go to §5 with no verification.

Once resolved (steps 2 and 3), persist the path at once, so the refine stage and any resume reuse it without prompting again: `uv run {stateScript} set-campaign --state-file {stateFile} --architecture-doc-path <path>`. Then proceed to §4 with the resolved path.

### §4: Invoke VS

Invoke `skf-verify-stack` with `--headless --architecture-doc <path>`, where `<path>` is the architecture doc §3 resolved.

VS discovers skills from its own configured `{skills_output_folder}`; the campaign does NOT pass individual skill paths. Keep the `SKF_VERIFY_STACK_RESULT_JSON` line it prints on stdout for §5. Its fields are defined once, by `shared/scripts/schemas/skf-verify-stack-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development); §5 reads `report_path`, `overall_verdict`, `coverage_percentage` and `recommendation_count` from it.

### §5: Record the VS Outcome and Complete the Stage

Record the outcome and the stage in one write, passing the §4 envelope line to the helper, which reads it (never copy its fields by hand):

```
uv run {stateScript} set-campaign --state-file {stateFile} --verification - --stage 7 <<'SKF_RESULT'
<the SKF_VERIFY_STACK_RESULT_JSON line VS printed>
SKF_RESULT
```

**On success** (`status` `success`, exit code 0), the helper persists the summary to `campaign.verification` (detailed findings stay in the external report):

- `campaign.verification.report_path`: `report_path` from the envelope, the timestamped report no later Verify Stack run rewrites (step-09 hands it to RA)
- `campaign.verification.overall_verdict`: `overall_verdict` from the envelope, one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE` or `NOT_FEASIBLE`
- `campaign.verification.coverage_percentage`: from the envelope
- `campaign.verification.recommendation_count`: from the envelope

It also sets `campaign.capstone.verified` to `true` when `overall_verdict` is `FEASIBLE`, otherwise `false` (only if a `campaign.capstone` entry exists from step-07).

**On VS failure** (a non-zero exit, an `error` envelope): the helper sets `campaign.verification` to `null` and names it in `not_recorded`; log the exit code and `halt_reason` (from the envelope or stderr, type `event`). Verification failure does NOT block the campaign: it produces diagnostic information for operator review. When VS printed no envelope, or §3 skipped it, record no verification instead: `uv run {stateScript} set-campaign --state-file {stateFile} --no-verification --stage 7`.

## OUTPUT

Display verification summary: overall verdict (or "skipped" if architecture doc was not found), report path (if produced), and coverage percentage. Chain to `{nextStepFile}`.

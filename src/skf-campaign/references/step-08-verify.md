---
nextStepFile: 'step-09-refine.md'
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
3. If still not found: skip VS invocation with a warning; do not HALT. Log that verification was skipped due to missing architecture doc (type `event`) and go to §5 with no verification.

When step 2 finds it, persist the path at once, so the refine stage and any resume reuse it: `uv run {stateScript} set-campaign --state-file {stateFile} --architecture-doc-path <path>`. Then proceed to §4 with the resolved path.

### §4: Invoke VS

Invoke `skf-verify-stack` with `--headless --architecture-doc <path>`, where `<path>` is the architecture doc §3 resolved.

VS discovers skills from its own configured `{skills_output_folder}`; the campaign does NOT pass individual skill paths. Keep the `SKF_VERIFY_STACK_RESULT_JSON` line it prints for §5: on stdout, or on stderr when VS halts. Its fields are defined once, by `shared/scripts/schemas/skf-verify-stack-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development).

### §5: Record the VS Outcome and Complete the Stage

Record the outcome and the stage in one write, passing the §4 envelope line to the helper, which reads it (never copy its fields by hand):

```
uv run {stateScript} set-campaign --state-file {stateFile} --verification - --stage 7 <<'SKF_RESULT'
<the SKF_VERIFY_STACK_RESULT_JSON line VS printed>
SKF_RESULT
```

**On VS failure** (a line whose `status` is `error` or whose `exit_code` is non-zero): the helper sets `campaign.verification` to `null` and names it in `not_recorded`; log that line's `exit_code` and `halt_reason` (type `event`). Verification failure does NOT block the campaign: it produces diagnostic information for operator review. When §3 skipped VS, record no verification instead: `uv run {stateScript} set-campaign --state-file {stateFile} --no-verification --stage 7`. When VS printed no `SKF_VERIFY_STACK_RESULT_JSON` line on stdout or stderr, there is no result to read, whatever its exit code: record it with `uv run {stateScript} set-campaign --state-file {stateFile} --no-result verification --stage 7`, log "no SKF_VERIFY_STACK_RESULT_JSON line (exit <code>)" with VS's exit code (type `event`), and go on. When the helper's `not_recorded` row gives the halt reason `result-unreadable` (VS printed a line that does not parse, or one with no `status` or `exit_code`), log "unparseable SKF_VERIFY_STACK_RESULT_JSON line" (type `event`) and go on.

## OUTPUT

Display verification summary: overall verdict (or "skipped" if architecture doc was not found, or "failed (<halt_reason>)" from the helper's `not_recorded` row), report path (if produced), and coverage percentage. That row's `halt_reason` fills it (`failed (no-result)` when VS printed no line); when that is null, show `failed (exit <exit_code>)`, or `failed (no exit code)` when the exit code is null too. Chain to `{nextStepFile}`.

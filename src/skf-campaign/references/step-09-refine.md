---
nextStepFile: 'step-10-export.md'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
stateScript: 'scripts/campaign-state.py'
statusScript: 'scripts/campaign-status.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Refine

## STEP GOAL:

Invoke RA (skf-refine-architecture) in headless mode with the project's architecture document and VS feasibility report to produce a refined architecture. RA identifies gaps, issues, and improvements based on the generated skills and applies them to the architecture document.

## RULES

- Write `campaign.current_stage` = 8 only in this stage's final state write (§5), after the refinement is recorded: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. RA runs headless with `--headless`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3: Locate Inputs

**Architecture doc:** Use the same resolution strategy as step-08:

1. If `campaign.architecture_doc_path` is set in state and the file exists, use it directly (step-08 normally persists it).
2. Otherwise check `{project-root}/docs/architecture.md`, then `{project-root}/_bmad-output/planning-artifacts/architecture.md`.
3. If still not found: skip RA invocation with a warning; do not HALT. Log that refinement was skipped due to missing architecture doc (type `event`) and go to §5 with no refinement.

When step 2 finds it, persist the path if state does not hold it yet: `uv run {stateScript} set-campaign --state-file {stateFile} --architecture-doc-path <path>`. Then proceed to §4 with the resolved path.

**VS feasibility report:** read `campaign.verification.report_path` from state, where step-08 saved the report VS wrote, so a chained run and a resumed one pass the same report. When it is null, or `campaign.verification` is unset (VS failed or step-08 skipped it), RA runs without a report: never look for one by file name.

### §4: Invoke RA

Invoke `skf-refine-architecture` with:

```
skf-refine-architecture --headless --architecture-doc <arch_path> --vs-report-path <report_path|none> [--scope-skills <names>]
```

- `--architecture-doc`: the architecture doc discovered in §3 (required).
- `--vs-report-path`: `campaign.verification.report_path` from §3, or `none` when state holds no report path.
- `--scope-skills`: the line `uv run {statusScript} --state-file {stateFile} --export-names` prints, unchanged: each completed skill's folder name, the name Refine Architecture's inventory knows. Leave the flag out when that line is empty or the call exits non-zero.

Keep the `SKF_REFINE_ARCHITECTURE_RESULT_JSON` line it prints for §5: on stdout, or on stderr when RA halts. Its fields are defined once, by `shared/scripts/schemas/skf-refine-architecture-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development).

### §5: Record the RA Outcome and Complete the Stage

Record the outcome and the stage in one write, passing the §4 envelope line to the helper, which reads it (never copy its fields by hand):

```
uv run {stateScript} set-campaign --state-file {stateFile} --refinement - --stage 8 <<'SKF_RESULT'
<the SKF_REFINE_ARCHITECTURE_RESULT_JSON line RA printed>
SKF_RESULT
```

**On RA failure** (a line whose `status` is `error` or whose `exit_code` is non-zero): the helper sets `campaign.refinement` to `null` and names it in `not_recorded`; log that line's `exit_code` and `halt_reason` (type `event`). Refinement failure does NOT block the campaign: the campaign continues to export with whatever state exists. When §3 skipped RA, record no refinement instead: `uv run {stateScript} set-campaign --state-file {stateFile} --no-refinement --stage 8`. When RA printed no `SKF_REFINE_ARCHITECTURE_RESULT_JSON` line on stdout or stderr, there is no result to read, whatever its exit code: record it with `uv run {stateScript} set-campaign --state-file {stateFile} --no-result refinement --stage 8`, log "no SKF_REFINE_ARCHITECTURE_RESULT_JSON line (exit <code>)" with RA's exit code (type `event`), and go on. When the helper's `not_recorded` row gives the halt reason `result-unreadable` (RA printed a line that does not parse, or one with no `status` or `exit_code`), log "unparseable SKF_REFINE_ARCHITECTURE_RESULT_JSON line" (type `event`) and go on.

## OUTPUT

Display refinement summary: refined architecture path (or "skipped" if architecture doc was not found, or "failed (<halt_reason>)" from the helper's `not_recorded` row), gap count, issue count, and improvement count. That row's `halt_reason` fills it (`failed (no-result)` when RA printed no line); when that is null, show `failed (exit <exit_code>)`, or `failed (no exit code)` when the exit code is null too. Chain to `{nextStepFile}`.

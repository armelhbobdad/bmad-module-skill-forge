---
nextStepFile: 'step-10-export.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
stateScript: 'scripts/campaign-state.py'
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
3. If still not found and `{headless_mode}` is false: prompt the operator.
4. If still not found and `{headless_mode}` is true: skip RA invocation with a warning; do not HALT. Log that refinement was skipped due to missing architecture doc (type `event`) and go to §5 with no refinement.

Once resolved (steps 2 and 3), persist the path if state does not hold it yet: `uv run {stateScript} set-campaign --state-file {stateFile} --architecture-doc-path <path>`. Then proceed to §4 with the resolved path.

**VS feasibility report:** read `campaign.verification.report_path` from state, where step-08 saved the report VS wrote, so a chained run and a resumed one pass the same report. When it is null, or `campaign.verification` is unset (VS failed or step-08 skipped it), RA runs without a report: never look for one by file name.

### §4: Invoke RA

Invoke `skf-refine-architecture` with:

```
skf-refine-architecture --headless --architecture-doc <arch_path> --vs-report-path <report_path|none> [--scope-skills <names>]
```

- `--architecture-doc`: the architecture doc discovered in §3 (required).
- `--vs-report-path`: `campaign.verification.report_path` from §3, or `none` when state holds no report path.
- `--scope-skills`: comma-separated names of completed campaign skills (from `skills[]` where `status == "completed"`). Optional but improves focus by limiting refinement scope to campaign-relevant skills.

Keep the `SKF_REFINE_ARCHITECTURE_RESULT_JSON` line it prints on stdout for §5. Its fields are defined once, by `shared/scripts/schemas/skf-refine-architecture-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development); §5 reads `status`, `refined_path`, `gap_count`, `issue_count` and `improvement_count` from it.

### §5: Record the RA Outcome and Complete the Stage

Record the outcome and the stage in one write, passing the §4 envelope line to the helper, which reads it (never copy its fields by hand):

```
uv run {stateScript} set-campaign --state-file {stateFile} --refinement - --stage 8 <<'SKF_RESULT'
<the SKF_REFINE_ARCHITECTURE_RESULT_JSON line RA printed>
SKF_RESULT
```

**On success** (`status` `success`, exit code 0), the helper persists the summary to `campaign.refinement` (the refined document itself lives at `refined_path`):

- `campaign.refinement.refined_path`: from the envelope
- `campaign.refinement.gap_count`: from the envelope
- `campaign.refinement.issue_count`: from the envelope
- `campaign.refinement.improvement_count`: from the envelope

**On RA failure** (a non-zero exit, an `error` envelope): the helper sets `campaign.refinement` to `null` and names it in `not_recorded`; log the exit code and `halt_reason` (from the envelope or stderr, type `event`). Refinement failure does NOT block the campaign: the campaign continues to export with whatever state exists. When RA printed no envelope, or §3 skipped it, record no refinement instead: `uv run {stateScript} set-campaign --state-file {stateFile} --no-refinement --stage 8`.

## OUTPUT

Display refinement summary: refined architecture path (or "skipped" if architecture doc was not found), gap count, issue count, and improvement count. Chain to `{nextStepFile}`.

---
nextStepFile: 'step-09-refine.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Verify

## STEP GOAL:

Invoke VS (skf-verify-stack) in headless mode against all completed campaign skills to produce a feasibility report. The report cross-references generated skills against the project's architecture document, providing coverage analysis and integration verdicts for operator review.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `7`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. VS supports headless via `--headless`.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3 — Locate Architecture Doc

Resolve the architecture document path, preferring the value persisted in state:

1. If `campaign.architecture_doc_path` is set in state and the file exists, use it directly.
2. Otherwise discover it: check `docs/architecture.md` at `{project-root}` (SKF convention), then `_bmad-output/planning-artifacts/architecture.md` (BMM convention).
3. If still not found and `{headless_mode}` is false: prompt the operator to provide the architecture doc path.
4. If still not found and `{headless_mode}` is true: skip VS invocation with a warning — do not HALT. Log that verification was skipped due to missing architecture doc (to the decision log) and proceed to §6.

Once resolved (steps 2–3), persist the path to `campaign.architecture_doc_path` so the refine stage and any resume reuse it without re-prompting. Then proceed to §4 with the resolved path.

### §4 — Invoke VS

Invoke `skf-verify-stack` with `--headless --architecture-doc <path>`, where `<path>` is the architecture doc discovered in §3.

VS discovers skills from its own configured `{skills_output_folder}` — the campaign does NOT pass individual skill paths. Capture the result envelope from stdout:

```
SKF_VERIFY_STACK_RESULT_JSON: {"status":"…","report_path":"…","report_latest_path":"…","overall_verdict":"…","coverage_percentage":0,"recommendation_count":0,"exit_code":0,"halt_reason":null}
```

### §5 — Handle VS Outcome

**On success** (exit code 0): persist the summary to `campaign.verification` (detailed findings stay in the external report):

- `campaign.verification.report_path` — `report_latest_path` from the envelope
- `campaign.verification.overall_verdict` — one of `Verified`, `Plausible`, `Risky`, `Blocked`
- `campaign.verification.coverage_percentage` — from the envelope
- `campaign.verification.recommendation_count` — from the envelope

Also set `campaign.capstone.verified` to `true` when `overall_verdict == "Verified"`, otherwise `false` (only if a `campaign.capstone` entry exists from step-07).

**On VS failure** (non-zero exit): log the error (exit code and halt_reason from the envelope or stderr). Verification failure does NOT block the campaign — it produces diagnostic information for operator review. Leave `campaign.verification` unset (or null). Continue to §6 regardless of outcome.

### §6 — Stage Completion

Set `campaign.current_stage` to `7`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state (including `campaign.architecture_doc_path` from §3 and `campaign.verification` from §5).

## OUTPUT

Display verification summary: overall verdict (or "skipped" if architecture doc was not found), report path (if produced), and coverage percentage. Chain to `{nextStepFile}`.

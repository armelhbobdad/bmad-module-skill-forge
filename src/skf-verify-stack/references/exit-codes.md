# Exit Codes and Result Envelope

Every hard halt in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text. Each code pairs with a `halt_reason` string carried in the headless result envelope. This file stands alone: a halting stage needs nothing else in context to emit its envelope.

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless missing `architecture-doc` arg, or invalid path) → `input-missing`; non-existent file → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (`{skills_output_folder}` does not exist or is empty → `skills-folder-missing`); step 1 pre-flight (forge_data_folder unconfigured → `forge-folder-unconfigured`); any stage that cannot resolve a required helper from its probe order (result emitter, atomic-write, schema ref, validate-feasibility-report, enumerate-stack-skills, comention-pairs, scan-skill-md-structure, find-cycles), or cannot start a helper it runs, the previous-report helper and the verdict rollup that find no shared report reader included → `resolution-failure` |
| 4    | write-failure        | step 1 pre-flight (the run folder or the write probe); steps 1 to 5 (a write of `{outputFile}`); step 6 §1 (the `-latest` copy); step 6 §4b (the emitter refuses the result payload twice) → `write-failed` |
| 5    | state-conflict       | step 1 §3 (fewer than 2 valid skills found: a stack requires ≥2 → `insufficient-skills`); step 1 §1 (in headless, `--previous-report` is `{outputFile}` or `{outputFileLatest}`, a file this run writes → `previous-report-collision`; an interactive run asks for another path); step 5 §1 (the report frontmatter lacks, or holds disagreeing, counts the verdict rollup reads → `schema-violation`); step 6 §1 (the report fails the feasibility-report check → `schema-violation`) |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; any prompt that accepted `cancel`/`exit`/`:q` |
| 7    | inventory-unreliable | step 1 §2 (enumerate-stack-skills warnings exceed its failure budget); step 3 §3 (>20% API-surface subagents return malformed JSON); skills SKF did not generate are not counted |

## Result Envelope

When `{headless_mode}` is true, step 6 prints one `SKF_VERIFY_STACK_RESULT_JSON: {...}` line on **stdout** before chaining to step 7, and every HARD HALT prints one on **stderr** with `status: "error"`. The shared emitter builds each line from the payload the stage stages in `{run_dir}`, folds in the decisions and warnings the run recorded there, and checks it against `{project-root}/_bmad/skf/shared/scripts/schemas/skf-verify-stack-result-envelope.v1.json` (`{project-root}/src/shared/scripts/schemas/skf-verify-stack-result-envelope.v1.json` in a dev checkout), whose descriptions say what each field holds: `status`, `report_path`, `report_latest_path`, `overall_verdict`, `coverage_percentage`, `recommendation_count`, `exit_code`, `halt_reason`, `run_id`, `result_path`, and `headless_decisions`, `warnings` and `error` when they apply. Never type the line yourself.

## Emitting a Halt

Every HALT names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"report_path": "{outputFile}"` once step 1 §4 wrote the report, `"report_latest_path": "{outputFileLatest}"` once step 6 §1 published it, and `"path"` when the halt names one. `{emitEnvelopeHelper}` is the first of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` that exists (each stage lists both as `emitEnvelopeProbeOrder`). Run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

The emitter sets `status: "error"`, derives `exit_code` from `halt_reason`, stamps `run_id` and gives every other field its default. Display the line it prints, then stop with the halt's exit code. If neither path exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT before the run folder exists passes the payload on stdin instead (init.md's pre-flight shows the command).

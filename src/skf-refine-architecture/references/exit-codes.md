# Exit Codes and Result Envelope

Every hard halt in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text. Each code pairs with a `halt_reason` string carried in the headless result envelope.

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless with no `--architecture-doc`) → `input-missing`; step 1 §1 (an architecture document that is missing or unreadable, or a [VS] report that breaks the feasibility-report contract (`schemaVersion` not `1.0`, a section missing or out of order, a missing or second verdict table, an unknown verdict token) or cannot be read), step 1 §1b and step 5 §6 and §8 (the architecture document cannot be read as UTF-8 text) → `input-invalid` |
| 3    | resolution-failure   | On Activation §5 (`output_folder` or `forge_data_folder` unconfigured → `output-folder-unconfigured` / `forge-folder-unconfigured`; the result emitter is not installed → `resolution-failure`); step 1 §1b, step 5 §6 and §8 and step 6 §1 (`scripts/skf-check-preservation.py` cannot start) → `resolution-failure` |
| 4    | write-failure        | On Activation §5 (the write probe, the run folder); step 1 §1b (the analysis copy); step 1 §3c (the RA state file); step 5 §6 (the draft) and §8 (the promotion, or a draft that still cannot be read after one rebuild); step 6 §1 (the result payload) and §4 (the emitter refuses it twice) → `write-failed`; step 5 §6 (in headless, the draft would lose or change a line of the original) and §8 (it still would after one rebuild) → `preservation-failed` |
| 5    | state-conflict       | step 1 §3 (no skill SKF generated was found: refinement requires ≥1 skill) → `insufficient-skills` |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; step 2 §2b scope confirmation `[X]`; any prompt that accepted `cancel`/`exit`/`:q`; step 5 review gate `[X]` (the draft is deleted, `{outputFile}` is unchanged); never step 6's final menu, where `[X]` finishes the run |
| 7    | inventory-unreliable | step 1 §2 (skill-inventory warnings exceed the failure budget); skills SKF did not generate are not counted |
| 8    | recovery-failed      | step 3 §4 (the [VS] report cannot be read again, or [VS] rewrote it during the run); step 5 §1 (the saved state is not enough to rebuild the Step 02-04 findings, the scope or the VS report); step 6 §1 (a record of the draft's build or promotion is missing) |

## Result Envelope

When `{headless_mode}` is true, step 6 prints one `SKF_REFINE_ARCHITECTURE_RESULT_JSON: {...}` line on **stdout** when it writes the result contract, before its final menu, and every HARD HALT prints one on **stderr** with `status: "error"`. The shared emitter builds each line from the payload the stage stages in `{run_dir}`, folds in the decisions and warnings the run recorded there, and checks it against `{project-root}/_bmad/skf/shared/scripts/schemas/skf-refine-architecture-result-envelope.v1.json` (`{project-root}/src/shared/scripts/schemas/skf-refine-architecture-result-envelope.v1.json` in a dev checkout), whose descriptions say what each field holds: `status`, `refined_path`, `previous_refined_path`, `previous_pass`, `gap_count`, `issue_count`, `improvement_count`, `unverified_count`, `exit_code`, `halt_reason`, `run_id`, `result_path`, and `headless_decisions`, `warnings` and `error` when they apply. Never type the line yourself.

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"insufficient-skills"`, `"output-folder-unconfigured"`, `"forge-folder-unconfigured"`, `"resolution-failure"`, `"inventory-unreliable"`, `"write-failed"`, `"preservation-failed"`, `"recovery-failed"`, `"user-cancelled"`. `exit_code` matches the table above, and the emitter derives it from `halt_reason`.

## Emitting a Halt

Every HALT names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"refined_path": "{outputFile}"` once step 5 promoted the draft and `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Each stage that halts shows this command and the probe order that resolves `{emitEnvelopeHelper}`, so a late halt emits the right line even when this file is not in context. Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT before the run folder exists (SKILL.md On Activation §5) passes the payload on stdin instead.

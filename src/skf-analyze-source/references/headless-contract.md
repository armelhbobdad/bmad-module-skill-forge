# Headless Result Contract & Exit Codes

Canonical headless/pipeline contract for skf-analyze-source. The shared emitter, `shared/scripts/skf-emit-result-envelope.py` (`{emitEnvelopeHelper}`, bound at SKILL.md On Activation §1), builds every line from the payload a step stages in `{run_dir}` and checks it against `shared/scripts/schemas/skf-analyze-result-envelope.v1.json`, so no step types an envelope.

## Result Envelope

The step that ends a run (step 6 §9, step 1a §9, or the docs-only branch §5) prints the envelope on **stdout** before chaining to step 7, and displays it when `{headless_mode}` is true. Every HARD HALT of a headless run prints it on **stderr** with `status: "error"`, so an automator branches on the failure class without grepping message text.

```
SKF_ANALYZE_RESULT_JSON: {"status":"success|error|redirect|skipped","report_path":"…|null","brief_paths":["…"],"unit_counts":{"confirmed":N,"skipped":N,"maybe":N},"exit_code":0,"halt_reason":null,"mode":"interactive|auto","result_path":"…|null"}
```

- `status`: `"success"` when the run ends, also with zero confirmed units (`brief_paths: []`, `unit_counts.confirmed: 0`); `"error"` on any HALT; `"redirect"` when coexistence routes to US (merge); `"skipped"` when the user skips a conflicting target.
- `halt_reason`: `null` unless the run halted, else one of `"input-missing"`, `"resolution-failure"`, `"pin-invalid"`, `"write-failed"`, `"user-cancelled"`. A brief the writer or the brief schema gate rejects halts with `"write-failed"`.
- `exit_code`: the emitter derives it from `halt_reason`, per the table below.
- `report_path`: absolute path to the analysis report, or `null` on a redirect, a skip and an early HALT.
- `brief_paths`: absolute path of every `skill-brief.yaml` the run wrote (empty array if none). A brief is written only after it passed the brief writer and, outside the docs-only branch, the schema gate.
- `unit_counts` — `confirmed` (units approved for briefs) and `skipped` (rejected in step 5, or the skipped target in coexistence §0c) counts; auto mode reports `confirmed:N, skipped:0`. `maybe` is a reserved slot, currently always `0`.
- `mode`: `"auto"` when the invocation carries `[auto]`, from activation through step 1a and the docs-only branch; `"interactive"` otherwise, also in the step-by-step chain an `[auto]` run falls back to (step 1a §3, exit 1).
- `result_path`: the per-run result file the emitter wrote, stamped by it; `null` for a HALT, which writes no result file, and when the write failed (a `result_file_write_failed` warning then says why).
- `error`: on a HALT only, `{"phase", "reason"}` plus `path` when the halt names one.
- `headless_decisions`: present when the run recorded an auto-decision: step 1a's §3b merge-or-split decision (gate `auto-scope.cohesion`) and its §5 choice of the documented language (gate `auto-scope.language`), and each gate default a headless run of the step-by-step chain took: `scan-project.scan`, `identify-units.classifications`, `map-and-detect.findings` (with the composite merges it accepted), `recommend.recommendations` and `generate-briefs.write`.
- `warnings`: present when the run recorded at least one.

In auto mode the envelope also carries `coexistence` (the §0c decision) and, when a pin resolves, `pinned_ref`/`pinned_version`; `step-auto-scope.md` §0b/§0c define those field semantics. A redirect adds `redirect_to`, `skill_name` and `skill_path`, a skip `skipped_reason`, and the docs-only path `source_type: "docs-only"`.

## Ending a Run

The step that ends the run stages `{run_dir}/result-context.json` with the envelope fields it knows and a `result_contract` object, the record the result files hold (`skill`, `status`, `outputs`, `summary`, per `shared/references/output-contract-schema.md`), and runs the emitter in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-analyze-source --run-dir "{run_dir}" --result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"
```

The emitter stamps the UTC time, the run id, the decisions and warnings the run recorded into the record, writes `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` and its `analyze-source-result-latest.json` copy, and prints the line. A result file that could not be written leaves `result_path` null and a `result_file_write_failed` warning in the line, and the run still finishes. If the emitter exits non-zero, the step corrects the payload from the message on its stderr and runs it once more; if it fails again, it HARD HALTs with exit code 4 (`write-failed`). Then `{onCompleteCommand}` runs, when it is set and `result_path` is not null, with `--result-path={forge_data_folder}/analyze-source-result-latest.json`; a hook failure is displayed and never fails the run. Last, the step deletes `{run_dir}` and chains to step 7.

## Halt Envelope

Every HARD HALT names its exit code, `halt_reason` and phase where it stops. In headless mode it prints its envelope before it stops: it stages `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "<auto or interactive>"}`, plus `"path"` when the halt names one, runs the first command below and displays the line it prints verbatim. A halt before SKILL.md On Activation §5 created `{run_dir}` hands that payload, on one line, to the second command. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. The emitter gives every field the payload leaves out its default (`null`, `[]`, zero counts, `"interactive"`) and derives `exit_code` from `halt_reason`. When the helper is missing, exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A halt writes no result file and keeps `{run_dir}`.

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --target stderr <<'SKF_ANALYZE_HALT'
{"phase": "on-activation:config", "reason": "<the halt message>", "halt_reason": "input-missing", "mode": "interactive"}
SKF_ANALYZE_HALT
```

Each step file states this rule in its own opening, so the HALTs of a step never depend on this file.

## Exit Codes

Every HARD HALT exits with a stable code so headless automators can branch on the failure class.

| Code | Meaning | Raised by |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / skipped / redirect | the step that ends the run: step 6 §9 (briefs written, or none when no unit was confirmed), step 1a §9, docs-only §5; coexistence `"skipped"`/`"redirect"` statuses from §0c |
| 2    | input-missing        | On Activation §2 (config.yaml not loadable); step 1 §2b (auto mode without `--project-path`); step 1 §3 (no project path in headless mode); step 1 §4 (`--target-refs` given with `--target-ref`, or a `--target-refs` key that matches no project path) |
| 3    | resolution-failure   | step 1 §2 (`forge-tier.yaml` missing at `{sidecar_path}/forge-tier.yaml`); step 1 §2b and §4 (project path does not exist or remote URL inaccessible, headless); step 1a §0a (docs-only URL unreachable); step 1a §0b (`halt_reason: "pin-invalid"` when the supplied `--pin` matches no tag or branch, `resolution-failure` when the pin helper fails); step 1a §2 (a remote path cannot be fetched, or the target's files cannot be listed); step 1a §3 (shape detection script error, exit code 2); step 2 §2 (a project path cannot be fetched at its ref); step 3 §1 and step 4 §1 (a scan root a resumed session makes again cannot be fetched); a shared helper script found at none of its probe paths (On Activation §1; step 1 §5; step 1a §0, §0b, §2, §3, §5 and §8, and its split branch; docs-only §2 and §4; step 2 §2; step 3 §2 and §4; step 4 §2, §3 and §5, and the [D] discover file of steps 4 and 5; step 6 §2) |
| 4    | write-failed         | On Activation §5 (the run folder cannot be created); step 1 §1 (an earlier report cannot be archived); a failed write of the analysis report (step 1 §6 / step 1a §7 / docs-only §3); a brief the writer or the schema gate rejects, or a brief write that fails (step 6 §3 and §5 / step 1a §8 / docs-only §4), and a brief that still fails a semantic check of step 6 §3 in headless mode; the emitter failing twice when the run ends (step 6 §9 / step 1a §9 / docs-only §5) |
| 6    | user-cancelled       | any interactive menu in steps 2/3/4/5/6 (user selected `[X]` Cancel and exit) |

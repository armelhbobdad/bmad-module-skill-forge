# Invocation Contract: skf-test-skill

The full argument set, gate map, outputs, exit codes and `SKF_TEST_RESULT_JSON` result envelope of `skf-test-skill`, and how a HALT prints its envelope. Interactive runs need none of it: headless automators and pipeline integrators read this file, and each stage's **Halt envelope** paragraph carries what a halting stage needs.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `skill_name` [required: an interactive run asks for it, a headless run without it halts `input-missing`; a path inside `{skills_output_folder}` names the skill folder it lies in]; optional flags: `--headless` / `-H` (or `headless_mode: true` in preferences.yaml), `--allow-workspace-drift`, `--no-discovery` (skip the report step's Discovery Testing block), `--no-health-check` (skip the health check that ends the run), `--tier=<Quick\|Forge\|Forge+\|Deep>` (test at this tier, bypassing the forge-tier.yaml sidecar requirement; it wins over `tier_override`; any other value halts `input-invalid`), `--threshold=<N>` (override the pass threshold; CLI wins over per-pipeline defaults and the `workflow.default_threshold` scalar), `--discovery-catalog=all` (widen the discovery catalog to the skills in `{project-root}/.claude/skills/` and `{project-root}/_bmad/agents/`) |
| **Gates** | none: every stage auto-proceeds, and the shared health check ends the run (its review gate defaults to [Q] in headless mode) |
| **Outputs** | the test report `test-report-{skill_name}-{run_id}.md` in `{forge_version}/`, written as `.skf-test-report-{skill_name}-{run_id}.md` until report.md §4c's checks pass (a run the hard gate blocked included), so a halted run never leaves a partial report under the name export-skill and update-skill read; the result contract `skf-test-skill-result-{YYYYMMDD-HHmmss}.json` and its `skf-test-skill-result-latest.json` copy in `{forge_version}/`, written by the shared emitter; `evidence-report-fallback.md` in `{forge_version}/` when the threshold fallback fires (a score between 80% and the target threshold, no cap fired); the gap ledger `test-findings-{run_id}.json` in `{forge_version}/`; for the run itself, a run folder `{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}/` holding the files the scripts hand each other, which report.md §7 removes (a HALT keeps it) |
| **Concurrency** | init.md §6a takes the run lock `{forge_version}/.test-skill.lock` through `skf-run-lock.py`, SKILL.md Workflow Rules renew it each time a subagent dispatch returns or, without subagents, the main thread finishes the work a step gives a subagent, each time the main thread finishes reading source files by eye, as each stage from detect-mode.md to report.md starts, and right before each subagent dispatch (report.md §4b.2's discovery subagents among them) or, without subagents, before the main thread starts the work a step gives a subagent, since it goes stale 60 minutes after it was taken or last renewed (a renewal right before a dispatch or that work passes `--stale-after 180`, a window the helper keeps in the lock, so no other run takes it over for 180 minutes while one dispatch runs, and the next renewal sets it back to 60), and report.md §4c renews it before it publishes the report and writes the result files; while another run holds a fresh lock, the run halts with `halt_reason: "another-run-active"` (exit 1). |
| **Headless** | No stage waits for an answer: a missing `skill_name` halts `input-missing`, the shared health check queues its findings locally, and the result envelope is the run's last line |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every terminal state settles one exit code, so a headless automator branches on the verdict, and on any HARD HALT, without grepping message text. A skill run cannot set the process exit status of the agent that runs it (`claude -p` exits 0 whatever the run decided), so automators read `exit_code` from the run's own `SKF_TEST_RESULT_JSON` line. A run that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result, and `skf-test-skill-result-latest.json` may then describe an earlier run, so it is never read in its place.

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / PASS       | step 6: `testResult: 'pass'`                                                               |
| 1    | error (HARD HALT)    | a HALT before a verdict exists, in steps 1 to 6: every `halt_reason` below but `hard-gate-blocked` |
| 2    | fail / FAIL          | step 4c §3: the hard gate blocked the run (`halt_reason: "hard-gate-blocked"`), and step 6 publishes it as a FAIL; step 6: `testResult: 'fail'` |
| 3    | inconclusive         | step 6: `testResult: 'inconclusive'` (distinct from fail so orchestrators can route to manual-review queues) |
| 4    | pass-with-drift      | step 6: `testResult: 'pass-with-drift'` (distinct from clean pass: `--allow-workspace-drift` was in effect and drift was observed; re-test against the pinned commit and refuse export, since exit 0 would wrongly signal a clean pass) |

## Result Envelope (Headless)

When `{headless_mode}` is true the run ends with one `SKF_TEST_RESULT_JSON: {...}` line. The shared emitter, `skf-emit-result-envelope.py`, builds every line from a payload the stage stages in `{run_dir}`, stamps `run_id` and `result_path`, and checks it against `{project-root}/_bmad/skf/shared/scripts/schemas/skf-test-result-envelope.v1.json` (`{project-root}/src/shared/scripts/schemas/skf-test-result-envelope.v1.json` in a development checkout), whose descriptions say what each field holds: `status`, `skill_name`, `verdict`, `score`, `threshold`, `report_path`, `next_workflow`, `exit_code`, `halt_reason`, `run_id`, `result_path`, and `threshold_fallback`, `original_threshold`, `warnings` and `error` when they apply. Never type the line yourself.

- **A finished run** (report.md §4c): `scripts/build-result-context.py` builds the payload from the report frontmatter, the gap ledger and the scoring output, deriving `verdict`, `exit_code` and `next_workflow` from `testResult`, and the emitter prints the line and writes the result files. `status` is `"success"` for a scored run (PASS, FAIL, INCONCLUSIVE or pass-with-drift) and `"error"` with `halt_reason: "hard-gate-blocked"` for a run the hard gate blocked (verdict `FAIL`, exit 2), which still writes the Gap Report and its FAIL result contract. `next_workflow` is `"export-skill"` only when `verdict` is `PASS`, `"update-skill"` for `FAIL` and `pass-with-drift`, null for `INCONCLUSIVE`. `threshold_fallback` (true) and `original_threshold` appear only when the threshold fallback fired.
- **A HALT** (below): `status: "error"`, the `halt_reason` of its failure class and the `exit_code` it maps to.
- **`warnings`**, on either line, lists each degradation the run recorded in its sink (SKILL.md Workflow Rules), one string each, starting with its code: `run-lock-replaced` (init.md §6b took over a stale run lock), `flat-skill-migrated` (init.md §2 moved a flat skill into a version folder), `metadata-missing` (the skill has no metadata.json), `workspace-drift-not-checked` (init.md §5b's drift helper could not read a source tree), `test-mode-defaulted-naive` (metadata.json's `skill_type` is neither `single` nor `stack`, so detect-mode.md §1 chose naive mode), `skill-check-unavailable` (skill-check did not run: `not-available`, `timeout-120s` or `no-json`, with the Gap Report's Info `skill-check not run` gap) and `tessl-review` (a warning Tessl Review raised), beside `customization_resolver_unavailable` and the emitter's own `result_file_write_failed`.

The emitter prints a finished run's line on stdout and a halt's or a blocked run's on stderr; the run displays the line either way, so the split is a label only. The line is the run's last line: report.md binds `{result_envelope_line}` to it and the shared health check displays it after everything else (report.md §7 displays it itself under `--no-health-check`), and a HALT displays its line and stops.

| `halt_reason` | Raised by |
| --- | --- |
| `input-missing` | init.md §1: a headless run given no skill name |
| `input-invalid` | init.md §1: a `--tier` value that names no tier; init.md §6c: a report template that is missing or lacks an anchor the stages write in |
| `runtime-missing` | SKILL.md On Activation step 1: `uv` is not on `PATH`; init.md §0b: `python3` or `uv` is not on `PATH` |
| `helper-missing` | an SKF helper the run needs is not installed: SKILL.md On Activation step 1 (`skf-preflight.py`), init.md §1, §2, §3a, §4 (`skf-forge-tier-rw.py`, unless `--tier` was passed), §5b and §6a, coherence-check.md §1 |
| `helper-failed` | a helper or a script that exits with an error the step cannot correct: SKILL.md On Activation step 1 (a config `skf-preflight.py` cannot load, its `code` such as `CONFIG_MISSING` in the message), init.md §2, §4 and §6b, the coverage and coherence steps' scripts, external-validators.md §4 and §5b, step 4c §2, score.md §3c and §6, report.md §4b and §4c, the lock renewals of SKILL.md Workflow Rules |
| `write-failed` | init.md §6b and §6c (the run folder or the report), report.md §4c (the report's public name, or the result contract the emitter refused twice) |
| `target-inaccessible` | init.md §2: no version of the skill to test |
| `not-skf-output` | init.md §2: a flat skill SKF did not generate |
| `frontmatter-invalid` | init.md §3b |
| `forge-tier-missing` | init.md §4: forge-tier.yaml is not there, or `skf-forge-tier-rw.py` cannot read a tier from it (a truncated or corrupted file) |
| `workspace-drift` | init.md §5b |
| `another-run-active` | init.md §6b, the lock renewals of SKILL.md Workflow Rules, and the lock renewal in report.md §4c |
| `inventory-invalid` | coverage-check.md §1a: the documented inventory failed its schema check, spot-check or floor check twice |
| `indeterminate-surface` | coverage-check.md §2b: zero exports, an empty stack surface or a docs-only skill that documents nothing, so no score can be attached |
| `step-completeness-violation` | step 4c §2 (a stage recorded nothing in the gap ledger) and report.md §4c |
| `report-anchor-missing` | report.md §4c |
| `health-check-missing` | report.md §4c, before anything is published |
| `hard-gate-blocked` | step 4c §3: not a halt, the run ends through report.md and publishes its FAIL |

When the emitter itself is not installed (init.md §0), no line can be printed: that HALT displays its message alone. A HALT at SKILL.md On Activation step 1 prints its line only under `--headless` or `-H`: that step runs the preflight that reads `headless_mode` from preferences.yaml, so a run made headless by that setting alone displays the message alone there.

## Result Files

report.md §4c runs the emitter with `--result-dir "{forge_version}"`. It writes the per-run record `skf-test-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name, `-2`, `-3` appended when a run already took that second's name) and then its copy `skf-test-skill-result-latest.json`, the record of the last run whose emitter wrote this copy, at a stable path (a copy, not a symlink), each atomically. The record holds the envelope's fields, plus `skill`, `outputs[]` (the published report), `summary` (`score`, `threshold`, `result` (`PASS`, `PASS_WITH_DRIFT`, `FAIL` or `INCONCLUSIVE`), `testMode`, `activeCategories[]`, `inconclusiveReasons[]` when present, `capReason` when a cap fired (the tooling to restore before testing again, since no skill edit lifts a cap; `next_workflow` still says `update-skill`), `threshold_fallback`, `original_threshold` and `evidence_report_path` when the threshold fallback fired, `gapCounts` with the gap ledger's gaps by severity, and `hardGate`), `runId` and `healthCheckDispatched`, and the emitter stamps `timestamp`, `run_id`, `headless_decisions` and `warnings` into it. A run the hard gate blocked writes it too, as a FAIL record, so its `skf-test-skill-result-latest.json` holds that FAIL, not an earlier run's verdict, unless the run's line holds a `result_file_write_failed` warning (the emitter stops at the first write that fails). A HALT writes no result file, and neither does a run cut off before report.md §4c: the copy then still holds an earlier run's verdict.

## Emitting a Halt

Every HALT names its `halt_reason` and its phase (`<step>:<check>`, such as `init:runtime` or `report:anchors`) and, in headless mode, prints its envelope through the shared emitter's `emit-halt`, which sets `status: "error"` and derives `exit_code` 1 from the `halt_reason`. Each stage's **Halt envelope** paragraph holds the command, the payload and, once init.md §6a took the run lock, its release.

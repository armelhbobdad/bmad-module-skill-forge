# Pipeline Mode Execution

The forger enters this procedure when the user supplies multiple workflow codes (e.g. `BS CS TS EX`, `QS TS EX`) or a pipeline alias (`forge`, `forge-auto`, `forge-quick`, `maintain`). It chains the workflows left to right, forwarding each output to the next input.

Load `shared/references/pipeline-contracts.md` for the alias-expansion table, the Data Flow output→input map, circuit-breaker thresholds, bracket syntax, and the anti-pattern list. This file covers the run procedure that consumes those tables.

## Activation

1. **Parse the sequence** — run `uv run scripts/parse-pipeline.py '<sequence>'` (from the skf-forger skill root). It tokenizes (space or arrow separated), expands aliases, classifies each bracket argument (`CS[cocoindex]` → target, `TS[min:80]` → circuit-breaker override, `AN[auto]` → mode flag), and returns the normalized `plan`/`codes` plus any `anti_patterns` as JSON. Consume that output rather than re-deriving the expansion or checks by hand. `deepwiki`/`onboard` are already resolved at recognition before this procedure runs, so the sequence reaching this step is normalized. If the script cannot run, fall back to expanding aliases against the pipeline-contracts.md alias table and applying its anti-pattern table by hand.

2. **Validate the sequence** — the parse output's `anti_patterns` array already lists any matches (EX before TS, CS without a brief, duplicate codes, US without AS), each with a message and suggestion. If it is non-empty, warn the user and ask to confirm or adjust. In `{headless_mode}`, warn but proceed.

3. **Force `{headless_mode}` = true** — pipelines auto-activate headless mode for every workflow in the chain; the user committed to the sequence by providing it.

4. **Execute left to right** — for each workflow:
   - a. **Report start:** "Pipeline [{current}/{total}]: Starting {code} ({description})..."
   - b. **Resolve inputs** from the previous workflow's output using the Data Flow table in pipeline-contracts.md. Pass any produced `skill_name`, `brief_path`, or other handoff data as the input argument.
   - c. **Invoke the workflow** with `{headless_mode}` = true, `{pipeline_alias}` set to the alias name (`forge-auto`, `forge`, `forge-quick`, `maintain`, or `null` for ad-hoc sequences), and any resolved arguments.
   - d. **Check the circuit breaker** after completion — load the output artifact and validate it against the threshold (default, or user-specified via `[min:N]`). On failure, halt the pipeline and report what completed and what remains.
   - e. **Report completion:** "Pipeline [{current}/{total}]: {code} complete — {brief summary of output}."

5. **Pipeline summary** — after all workflows complete (or on halt), present: completed workflows with key outputs; the failed/halted workflow (if any) with its halt reason; remaining unexecuted workflows; and a next-steps recommendation.

6. **Result contract** — write the pipeline result contract per `shared/references/output-contract-schema.md`: the per-run record at `{sidecar_path}/pipeline-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{sidecar_path}/pipeline-result-latest.json` (stable path for consumers — copy, not symlink). Include one entry per completed workflow in `outputs` (each referencing that workflow's own `-latest.json` record); record per-step status for every workflow in the sequence — completed, halted, and not-yet-run — plus the overall pipeline status (`summary.status` — one of `success`, `failed`, or `partial`) in `summary`. On a `failed`/`partial` status, the forger's On Activation resume check reads that per-step record to offer continuation of the not-yet-run workflows.

## forge-auto argument passing

`forge-auto <repo-url> --pin <version>` — the `--pin` argument flows to AN's pipeline data context alongside the `[auto]` flag. AN's `step-auto-scope.md §0b` consumes it for pin resolution.

## Special behaviors

- **`AN` with `CS`:** if AN produces multiple recommended briefs, auto-select all and process them sequentially in batch mode. If only one unit is found, auto-select it.
- **`AS` followed by `US`:** if `summary.severity` in `audit-skill-result-latest.json` is CLEAN, skip US and report "No drift detected — skipping update."
- **`TS` followed by `EX`:** if the test result is FAIL and the score is below the circuit-breaker threshold, halt before EX.

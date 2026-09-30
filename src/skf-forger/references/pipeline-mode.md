# Pipeline Mode Execution

The forger enters this procedure from the Pipeline Mode section of its SKILL.md. It chains the workflows left to right, forwarding each output to the next input.

Load `shared/references/pipeline-contracts.md` for the alias-expansion table, the Data Flow output→input map, circuit-breaker thresholds, bracket syntax, and the anti-pattern list. This file covers the run procedure that consumes those tables.

## Activation

1. **Parse the invocation**: hand the parser the user's whole pipeline invocation, everything typed after `@Ferris` or `/skf-forger`: the codes, or the alias with the arguments after it (for example `forge-auto https://github.com/honojs/hono --pin v4.6.0` or `forge-quick cognee`), from the skf-forger skill root:

   ```bash
   uv run scripts/parse-pipeline.py --stdin <<'SKF_PIPELINE'
   <the whole invocation>
   SKF_PIPELINE
   ```

   It tokenizes (space or arrow separated), expands a leading alias and binds the arguments after it, classifies each bracket argument in any case (`CS[cocoindex]` → target, `TS[min:80]` → circuit-breaker override, `AN[auto]` → mode flag), and prints `plan`/`codes`, the first workflow's `args`, `alias`, any `anti_patterns` and `valid` as JSON. Consume that output rather than re-deriving the expansion or checks by hand, and branch on it before any workflow runs:

   - **No JSON object on stdout**: HALT with what the call printed as the reason. An exit 2 or 3 that prints its JSON is an answer, handled below.
   - **Exit 2** (`removed_alias` is `onboard`): HALT with "**onboard has been removed.** Use `forge-auto <repo-url>` instead. forge-auto auto-scopes, auto-briefs, and tests at 90% quality. Run `forge-auto` with any GitHub URL, doc URL, or `--pin <version>`."
   - **Exit 3** (`valid` is false): name each token in `unknown_codes`, `unexpected_args` and `malformed_brackets` (a bracket holds `min:<number>`, `auto` or a target) and each input in `missing_args` (an alias takes its argument after it, as in `forge-quick <package-or-url>`), ask the user for the corrected invocation, and parse that one. In `{headless_mode}`, ask nothing: HALT with those tokens as the reason.
   - **`deprecated_alias`** is `deepwiki`: say once "**`deepwiki` is now `forge-auto`.** The alias was renamed to avoid confusion with the DeepWiki MCP: this pipeline auto-forges a verified skill from source and does **not** call that MCP. `deepwiki` still works as a deprecated alias; prefer `forge-auto <repo-url>` going forward.", then go on with the plan, whose `alias` is `forge-auto`.

   A HALT in this step runs no workflow. In `{headless_mode}` it still writes the step 6 result contract, with `summary.status` `failed`, the halt reason in `summary.halt_reason` and no workflow in it: nothing ran, and an invocation that did not parse leaves nothing to resume.

2. **Validate the sequence**: the parse output's `anti_patterns` array already lists any matches (EX before TS, CS without a brief, duplicate codes, US without AS, a `min:N` on a code other than AN and TS), each with a message and suggestion. If it is non-empty, warn the user and ask to confirm or adjust. In `{headless_mode}`, warn but proceed.

3. **Force `{headless_mode}` = true**: pipelines auto-activate headless mode for every workflow in the chain; the user committed to the sequence by providing it.

4. **Execute left to right.** For each workflow:
   - a. **Report start:** "Pipeline [{current}/{total}]: Starting {code} ({description})..."
   - b. **Resolve inputs** from the previous workflow's output using the Data Flow table in pipeline-contracts.md. Pass any produced `skill_name`, `brief_path`, or other handoff data as the input argument. The first workflow takes the parse's `args` instead: each key names the input it fills (`project_path`, `target_repo`, `skill_name` or `target`), and `pin` goes to its data context, as the pipeline-contracts.md Pipeline Arguments section says.
   - c. **Invoke the workflow** with `{headless_mode}` = true, `{pipeline_mode}` = true, `{pipeline_alias}` set to the parse's `alias` (`forge-auto`, `forge`, `forge-quick`, `maintain`, or `null` for ad-hoc sequences), and any resolved arguments. When TS's plan entry has a `min`, invoke TS with `--threshold=<min>`: TS applies it, with its caps and its 80% floor fallback, and settles the verdict step d reads. `{pipeline_mode}` is how a workflow knows it runs inside a pipeline, since `{pipeline_alias}` is null for an ad-hoc sequence. When the workflow's last step finishes, control returns here: continue with d, even when that step reads as the end of the run.
   - d. **Check the circuit breaker.** After AN, TS, AS or VS, run the gate on the result envelope line the workflow just printed (`SKF_ANALYZE_RESULT_JSON`, `SKF_TEST_RESULT_JSON`, `SKF_AUDIT_RESULT_JSON` or `SKF_VERIFY_STACK_RESULT_JSON`), from the skf-forger skill root:

     ```bash
     uv run scripts/pipeline-gate.py --code <code> [--next <next-code>] [--min <N>] <<'SKF_RESULT'
     <the SKF_*_RESULT_JSON line>
     SKF_RESULT
     ```

     Gate that line only, never a `-latest.json` result file: a workflow can halt after writing its file, or abort before writing one, so the file may not describe this run. When the workflow printed no envelope line, leave the heredoc empty: the gate halts with `no-result`. Give `--next` the next code in the plan and, for AN with a `min` in its plan entry, `--min` that value. The gate prints one JSON object; act on its `decision`: `continue` goes on, `skip` reports `message` and passes over the next workflow (`skip` names it), and `halt` stops the pipeline with `reason` as the halt reason (for TS, the verdict: `FAIL`, `INCONCLUSIVE` or `pass-with-drift`), then reports what completed and what remains. A gate that prints no JSON halts the pipeline as well, with what it printed as the reason. Compare no score with a threshold here: TS took `[min:N]` as `--threshold` in c and settled its own verdict. The other workflows have no gate: one that hard-halts stops the pipeline (the Pipeline Rules in pipeline-contracts.md), which is CS's circuit breaker, and SF follows its entry under Special behaviors.
   - e. **Report completion:** "Pipeline [{current}/{total}]: {code} complete ({brief summary of output})."

5. **Pipeline summary.** After all workflows complete (or on halt), present: completed workflows with key outputs; the failed/halted workflow (if any) with its halt reason; remaining unexecuted workflows; and a next-steps recommendation.

6. **Result contract**: write the pipeline result contract per `shared/references/output-contract-schema.md`: the per-run record at `{sidecar_path}/pipeline-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{sidecar_path}/pipeline-result-latest.json` (stable path for consumers: copy, not symlink). Include one entry per completed workflow in `outputs` (each referencing that workflow's own `-latest.json` record); record per-step status for every workflow in the sequence (completed, halted, and not-yet-run), plus the overall pipeline status (`summary.status`: one of `success`, `failed`, or `partial`) and, on a halt, its reason (`summary.halt_reason`) in `summary`. On a `failed`/`partial` status, the forger's On Activation resume check reads that per-step record to offer continuation of the not-yet-run workflows.

## Special behaviors

- **`AN` with `CS`:** if AN produces multiple recommended briefs, auto-select all and process them sequentially in batch mode. If only one unit is found, auto-select it.
- **`TS` followed by `EX`:** EX runs only when the gate continues after TS, which it does for the settled verdict PASS alone (`next_workflow` `export-skill`). FAIL, INCONCLUSIVE and pass-with-drift halt before EX with the verdict as the halt reason, including a FAIL that a post-score cap forced although its score clears the threshold.
- **`SF` in a sequence:** SF writes no result file; the one `SKF_SETUP_RESULT_JSON` envelope line it displays is its output. Continue on `status` `success`. Any other status halts the pipeline, with that status and any `error.reason` as the halt reason; so does a run that displays no envelope line, with the line it did display as the reason.

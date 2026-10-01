# Pipeline Mode Execution

## Activation

1. **Parse the invocation**: hand the parser the user's whole pipeline invocation, everything typed after `@Ferris` or `/skf-forger`: the codes, or the alias with the arguments after it (for example `forge-auto https://github.com/honojs/hono --pin v4.6.0` or `forge-quick cognee`), from the skf-forger skill root:

   ```bash
   uv run scripts/parse-pipeline.py --stdin <<'SKF_PIPELINE'
   <the whole invocation>
   SKF_PIPELINE
   ```

   It prints `plan`/`codes`, the first workflow's `args`, `alias`, any `anti_patterns` and `valid` as JSON. Consume that output rather than re-deriving the expansion or checks by hand, and branch on it before any workflow runs:

   - **No JSON object on stdout**: HALT with what the call printed as the reason. An exit 2 or 3 that prints its JSON is an answer, handled below.
   - **Exit 2** (`removed_alias` is `onboard`): HALT with "**onboard has been removed.** Use `forge-auto <repo-url>` instead. forge-auto auto-scopes, auto-briefs, and tests at 90% quality. Run `forge-auto` with any GitHub URL, doc URL, or `--pin <version>`."
   - **Exit 3** (`valid` is false): name each token in `unknown_codes`, `unexpected_args` and `malformed_brackets` (a bracket holds `min:<number>`, `auto` or a target) and each input in `missing_args` (an alias takes its argument after it, as in `forge-quick <package-or-url>`), ask the user for the corrected invocation, and parse that one. In `{headless_mode}`, ask nothing: HALT with those tokens as the reason.
   - **`deprecated_alias`** is `deepwiki`: say once "**`deepwiki` is now `forge-auto`.** The alias was renamed to avoid confusion with the DeepWiki MCP: this pipeline auto-forges a verified skill from source and does **not** call that MCP. `deepwiki` still works as a deprecated alias; prefer `forge-auto <repo-url>` going forward.", then go on with the plan, whose `alias` is `forge-auto`.

   A HALT in this step runs no workflow. In `{headless_mode}` it still writes the pipeline result, with `summary.status` `failed`, the halt reason in `summary.halt_reason` and no workflow in it, from the skf-forger skill root: `uv run scripts/pipeline-journal.py finish --result-dir "{sidecar_path}" --halt-reason '<the halt reason>'`. A reason given to a journal call goes in single quotes, with each `'` in it replaced by a backtick, so the shell runs nothing in it. Nothing ran, and an invocation that did not parse leaves nothing to resume.

2. **Validate the sequence**: the parse output's `anti_patterns` array already lists any matches (EX before TS, CS without a brief, duplicate codes, US without AS, a `min:N` on a code other than AN and TS), each with a message and suggestion. If it is non-empty, warn the user and ask to confirm or adjust. In `{headless_mode}`, warn but proceed.

3. **Force `{headless_mode}` = true**: pipelines auto-activate headless mode for every workflow in the chain; the user committed to the sequence by providing it.

4. **Execute left to right.** First start the run's journal, which keeps the chain's state on disk (Pipeline State in pipeline-contracts.md), with the invocation step 1 parsed, from the skf-forger skill root:

   ```bash
   uv run scripts/pipeline-journal.py start --run-root "{project-root}/_bmad-output/.skf-run" <<'SKF_PIPELINE'
   <the whole invocation>
   SKF_PIPELINE
   ```

   It prints the `journal` path, which every later journal call of this run names, and the `steps`. If it prints no JSON object, or its `status` is not `ok`, no workflow has run: write the failed pipeline result as step 1 does, with its `message` (or what it printed, when that is no JSON object) as the halt reason, then HALT with that reason. Then, for each workflow:
   - a. **Report start:** "Pipeline [{current}/{total}]: Starting {code} ({description})..."
   - b. **Resolve inputs** from the previous workflow's output using the Data Flow table in pipeline-contracts.md. Pass any produced `skill_name`, `brief_path`, or other handoff data as the input argument: the `data` the last `step` call printed holds each one. A `target_ref` in `data` (AS hands it on when upstream moved) goes to US as `--target-ref <target_ref>`. The first workflow takes the parse's `args` instead: each key names the input it fills (`project_path`, `target_repo`, `skill_name` or `target`), and `pin` goes to its data context, as the pipeline-contracts.md Pipeline Arguments section says.
   - c. **Invoke the workflow** with `{headless_mode}` = true, `{pipeline_mode}` = true, `{pipeline_alias}` set to the parse's `alias` (`forge-auto`, `forge`, `forge-quick`, `maintain`, or `null` for ad-hoc sequences), any resolved arguments, and the plan entry's `flags`. When TS's plan entry has a `min`, invoke TS with `--threshold=<min>`: TS applies it, with its caps and its 80% floor fallback, and settles the verdict step d reads. `{pipeline_mode}` is how a workflow knows it runs inside a pipeline, since `{pipeline_alias}` is null for an ad-hoc sequence. When the workflow's last step finishes, control returns here: continue with d, even when that step reads as the end of the run.
   - d. **Check the circuit breaker.** After AN, TS, AS or VS, run the gate on the result envelope line the workflow just printed (`SKF_ANALYZE_RESULT_JSON`, `SKF_TEST_RESULT_JSON`, `SKF_AUDIT_RESULT_JSON` or `SKF_VERIFY_STACK_RESULT_JSON`), from the skf-forger skill root:

     ```bash
     uv run scripts/pipeline-gate.py --code <code> [--next <next-code>] [--min <N>] <<'SKF_RESULT'
     <the SKF_*_RESULT_JSON line>
     SKF_RESULT
     ```

     Gate that line only, never a `-latest.json` result file: a workflow can halt after writing its file, or abort before writing one, so the file may not describe this run. When the workflow printed no envelope line, leave the heredoc empty: the gate halts with `no-result`. Give `--next` the next code in the plan and, for AN with a `min` in its plan entry, `--min` that value. The gate prints one JSON object; act on its `decision`: `continue` goes on, `skip` reports `message` and passes over the next workflow (`skip` names it), and `halt` stops the pipeline with `reason` as the halt reason (for TS, the verdict: `FAIL`, `INCONCLUSIVE` or `pass-with-drift`), then reports what completed and what remains. A gate that prints no JSON halts the pipeline as well, with what it printed as the reason. Compare no score with a threshold here: TS took `[min:N]` as `--threshold` in c and settled its own verdict. The other workflows have no gate: one that hard-halts stops the pipeline (the Pipeline Rules in pipeline-contracts.md), which is CS's circuit breaker, and SF follows its entry under Special behaviors.
   - e. **Record the step** in the journal before anything else, so a chain stopped from here on loses nothing. After AN, TS, AS or VS, hand it the JSON the gate printed: it records the step as the gate decided, and on a `skip` the workflow the gate passes over too:

     ```bash
     uv run scripts/pipeline-journal.py step --journal "<journal>" --code <code> --gate [--set "<name>=<value>"] [--output "<path>"] <<'SKF_GATE'
     <the JSON the gate printed>
     SKF_GATE
     ```

     After any other workflow, or when the gate printed no JSON, give the step's status: `completed`, or `halted` with the workflow's own halt reason (or what the gate printed):

     ```bash
     uv run scripts/pipeline-journal.py step --journal "<journal>" --code <code> --status <completed|halted> [--reason '<reason>'] [--set "<name>=<value>"] [--output "<path>"]
     ```

     Give `--set` each handoff value the workflow produced, by its Data Flow name: a completed CS, QS or US hands on `skill_name=<name>`, a completed AN or BS `brief_path=<path>`, and an AS whose envelope names an `upstream_ref` (it is not null when `upstream_moved` is true) `target_ref=<upstream_ref>`. Give `--output` the result or report path its envelope names. The call prints the `next` plan entry (null after a halt or the last step) and the run's `data`. An error with `retry` true means the call lacked what its `message` names: run it again with that. On any other error, or no JSON object, the chain stops, with the `message` (or what it printed) as the halt reason. After a halt, or when the chain stops, go to step 5; otherwise go on with f, then with the `next` entry, or with step 5 when there is none.
   - f. **Report completion:** "Pipeline [{current}/{total}]: {code} complete ({brief summary of output})."

5. **Result contract**: write the pipeline result from the journal, from the skf-forger skill root:

   ```bash
   uv run scripts/pipeline-journal.py finish --journal "<journal>" --result-dir "{sidecar_path}" [--halt-reason '<reason>']
   ```

   Give `--halt-reason` the reason the chain stopped with when no `step` call recorded it. The call prints the pipeline's `pipeline_status`, its `halt_reason` and, after a halt, its `route`: the next action. If it prints no JSON object, or its `status` is not `ok`, say so in step 6: the chain's own outcome stands.

6. **Pipeline summary.** After all workflows complete (or on halt), present: completed workflows with key outputs; the failed/halted workflow (if any) with its halt reason; remaining unexecuted workflows; and a next-steps recommendation, which after a halt is step 5's `route`.

## Resume

When the user accepts the offer On Activation step 4 made, run the chain from its journal instead of a new invocation: steps 1 and 2 are skipped, since the journal holds the plan the first parse produced. When the offer has a `user_action`, first confirm the user did it. Then, from the skf-forger skill root:

```bash
uv run scripts/pipeline-journal.py reopen --journal "<journal>"
```

`<journal>` is the path the offer named. The call prints the plan entries still to `run`, the `alias`, the first workflow's `args` and the handoff `data`. If it prints no JSON object, or its `status` is not `ok`, HALT with what it printed. Otherwise go on with step 3, then step 4 from the first entry of `run`, without step 4's `start` call (every `step` call names this `journal`): `{pipeline_alias}` is `alias`, each entry carries its bracket values and `flags`, and the first entry takes its `target` when it has one, else its Data Flow inputs from `data`, or from `args` when it is the plan's first workflow.

## Special behaviors

- **`SF` in a sequence:** SF writes no result file; the one `SKF_SETUP_RESULT_JSON` envelope line it displays is its output. Continue on `status` `success`. Any other status halts the pipeline, with that status and any `error.reason` as the halt reason; so does a run that displays no envelope line, with the line it did display as the reason.

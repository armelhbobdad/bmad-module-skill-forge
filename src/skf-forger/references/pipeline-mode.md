# Pipeline Mode Execution

Paths here resolve as the skf-forger SKILL.md **Conventions** say: each `uv run scripts/...` call runs from the skf-forger skill root (`{skill-root}`).

## Activation

1. **Parse the invocation**: hand the parser the user's whole pipeline invocation, everything typed after `@Ferris` or `/skf-forger`: the codes, or the alias with the arguments after it (for example `forge-auto https://github.com/honojs/hono --pin v4.6.0` or `forge-quick cognee`), from the skf-forger skill root:

   ```bash
   uv run scripts/parse-pipeline.py --stdin <<'SKF_PIPELINE'
   <the whole invocation>
   SKF_PIPELINE
   ```

   It prints `plan`/`codes`, the first workflow's `args`, `alias`, any `anti_patterns`, `first_input` and `valid` as JSON. Consume that output rather than re-deriving the expansion or checks by hand, and branch on it before any workflow runs:

   - **No JSON object on stdout**: HALT with what the call printed as the reason. An exit 2 or 3 that prints its JSON is an answer, handled below.
   - **Exit 2** (`removed_alias` is `onboard`): HALT with "**onboard has been removed.** Use `forge-auto <repo-url>` instead. forge-auto auto-scopes, auto-briefs, and tests at 90% quality. Run `forge-auto` with any GitHub URL, doc URL, or `--pin <version>`."
   - **Exit 3** (`valid` is false): name each token in `unknown_codes`, `unexpected_args` and `malformed_brackets` (a bracket holds `min:<number>`, `auto` or a target) and each input in `missing_args` (an alias takes its argument after it, as in `forge-quick <package-or-url>`), ask the user for the corrected invocation, and parse that one. In `{headless_mode}`, ask nothing: HALT with those tokens as the reason.
   - **`deprecated_alias`** is `deepwiki`: say once "**`deepwiki` is now `forge-auto`.** The alias was renamed to avoid confusion with the DeepWiki MCP: this pipeline auto-forges a verified skill from source and does **not** call that MCP. `deepwiki` still works as a deprecated alias; prefer `forge-auto <repo-url>` going forward.", then go on with the plan, whose `alias` is `forge-auto`.
   - **`first_input`** is set (`valid` is true, and the first workflow, past a leading `SF`, lacks the input it starts from, as for `QS TS EX` or `QS TS EX --pin 1.2.0`): the chain runs headless from step 3 on, so it cannot ask later. Ask the user for its `input`, then parse again its `form`, the invocation with the answer in place of each `<...>` placeholder, as `QS[cocoindex] TS EX`: step 4 starts the journal from that invocation. A null `form` means no chain can carry that input: say its `halt_reason`, ask the user for the corrected invocation, and parse that one. In `{headless_mode}`, ask nothing: HALT with its `halt_reason`, which for an input a bracket gives reads `<CODE> needs <input> before the pipeline can start: give it as <CODE>[<input>]`, such as `QS needs a target before the pipeline can start: give it as QS[<target>]`. A null `halt_reason` (a leading `CS`) halts nothing: go on with the chain, since create-skill compiles the only brief in `{forge_data_folder}`, and halts `brief-missing` naming the briefs when there are several.

   A HALT in this step runs no workflow. In `{headless_mode}` it still writes the pipeline result, with `summary.status` `failed`, the halt reason in `summary.halt_reason` and no workflow in it, from the skf-forger skill root: `uv run scripts/pipeline-journal.py finish --result-dir "{sidecar_path}" --halt-reason '<the halt reason>'`. A reason given to a journal call goes in single quotes, with each `'` in it replaced by a backtick, so the shell runs nothing in it. Nothing ran, and a halt here starts no journal, so it leaves nothing to resume.

2. **Validate the sequence**: the parse output's `anti_patterns` array already lists any matches (EX before TS, CS without a brief, duplicate codes, US without AS, a `min:N` on a code other than AN and TS), each with a message and suggestion. If it is non-empty, warn the user and ask to confirm or adjust. In `{headless_mode}`, warn but proceed.

3. **Force `{headless_mode}` = true**: pipelines auto-activate headless mode for every workflow in the chain; the user committed to the sequence by providing it.

4. **Execute left to right.** First start the run's journal, which keeps the chain's state on disk, with the invocation step 1 parsed, from the skf-forger skill root:

   ```bash
   uv run scripts/pipeline-journal.py start --run-root "{project-root}/_bmad-output/.skf-run" <<'SKF_PIPELINE'
   <the whole invocation>
   SKF_PIPELINE
   ```

   It prints the `journal` path, which every later journal call of this run names, the `steps`, and the `next` entry: the first workflow to run, with its `code`, bracket values and `flags`, its `skill` and `description`, and the `inputs` it runs with. If it prints no JSON object, or its `status` is not `ok`, no workflow has run: write the failed pipeline result as step 1 does, with its `message` (or what it printed, when that is no JSON object) as the halt reason, then HALT with that reason. Then run that `next` entry, and after it each `next` entry a `step` call prints:
   - a. **Report start:** "Pipeline [{current}/{total}]: Starting {code} ({description})...", with the entry's `code` and `description`.
   - b. **Resolve inputs** from the entry's `inputs`, which the journal already resolved: the entry's bracket `target` (`QS[cocoindex]` hands QS `cocoindex`), else the handoff values earlier steps recorded, else, for the plan's first workflow, the parse's `args`. Work out no input by hand. Each key names the input it fills (`target`, `project_path`, `target_repo`, `skill_name`, `brief_path` or `architecture_doc_path`), and some go their own way: a `batch` list names several briefs, which go to CS as one `--batch` run; a `target_ref` (AS hands it on when upstream moved) goes to US as `--target-ref <target_ref>`; RA's `architecture_doc_path` is the document VS was given; and `pin` goes to the workflow's data context. Step c passes `auto`, `threshold` and `flags`.
   - c. **Invoke the workflow**: invoke the entry's `skill`, by that exact name, with `{headless_mode}` = true, `{pipeline_mode}` = true, `{pipeline_alias}` set to the parse's `alias` (`forge-auto`, `forge`, `forge-quick`, `maintain`, or `null` for ad-hoc sequences), its `inputs` as step b passes them, and any `flags` in them as given (`--from-test-report`). An `auto` in `inputs` invokes the workflow as `<code>[auto]` (`AN[auto]`, `BS[auto]`), which routes it to its auto-mode steps. A `threshold` in `inputs` is TS's plan `min`, so invoke TS with `--threshold=<min>`: TS applies it, with its caps and its 80% floor fallback, and settles the verdict step d reads. `{pipeline_mode}` is how a workflow knows it runs inside a pipeline, since `{pipeline_alias}` is null for an ad-hoc sequence. When the workflow's last step finishes, control returns here: continue with d, even when that step reads as the end of the run.
   - d. **Check the circuit breaker.** After AN, TS, AS or VS, run the gate on the result envelope line the workflow just printed (`SKF_ANALYZE_RESULT_JSON`, `SKF_TEST_RESULT_JSON`, `SKF_AUDIT_RESULT_JSON` or `SKF_VERIFY_STACK_RESULT_JSON`), from the skf-forger skill root:

     ```bash
     uv run scripts/pipeline-gate.py --code <code> [--next <next-code>] [--min <N>] <<'SKF_RESULT'
     <the SKF_*_RESULT_JSON line>
     SKF_RESULT
     ```

     Gate that line only, never a `-latest.json` result file: a workflow can halt after writing its file, or abort before writing one, so the file may not describe this run. When the workflow printed no envelope line, leave the heredoc empty: the gate halts with `no-result`. Give `--next` the next code in the plan and, for AN with a `min` in its plan entry, `--min` that value. The gate prints one JSON object; act on its `decision`: `continue` goes on, `skip` reports `message` and passes over the next workflow (`skip` names it), and `halt` stops the pipeline with `reason` as the halt reason (for TS, the verdict: `FAIL`, `INCONCLUSIVE` or `pass-with-drift`), then reports what completed and what remains. A gate that prints no JSON halts the pipeline as well, with what it printed as the reason. Compare no score with a threshold here: TS took `[min:N]` as `--threshold` in c and settled its own verdict. The other workflows have no gate: one that hard-halts stops the pipeline, which is CS's circuit breaker, and SF follows its entry under Special behaviors.
   - e. **Record the step** in the journal before anything else, so a chain stopped from here on loses nothing. After AN, TS, AS or VS, hand it the JSON the gate printed: it records the step as the gate decided, and on a `skip` the workflow the gate passes over too:

     ```bash
     uv run scripts/pipeline-journal.py step --journal "<journal>" --code <code> --gate [--set "<name>=<value>"] [--output "<path>"] <<'SKF_GATE'
     <the JSON the gate printed>
     SKF_GATE
     ```

     After any other workflow, or when the gate printed no JSON, give the step's status: `completed`, or `halted` with the workflow's own halt reason (or what the gate printed). An ungated workflow (CS, BS, QS, US, EX, SS, RA, DS, RS) that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result, so record it `halted` with `--reason no-result`, as the gate halts a gated one:

     ```bash
     uv run scripts/pipeline-journal.py step --journal "<journal>" --code <code> --status <completed|halted> [--reason '<reason>'] [--set "<name>=<value>"] [--output "<path>"]
     ```

     Give `--set` each handoff value the workflow produced, by its handoff name: a completed CS, QS or US hands on `skill_name=<name>`, and a completed AN or BS `brief_path=<path>`. AS's `target_ref` takes no `--set`: when upstream moved, the gate prints it in its `handoff`, and `step --gate` records it. Give `--output` the result or report path its envelope names. The call prints the `next` plan entry, with its `skill`, `description` and `inputs` (null after a halt or the last step), and the run's `data`. An error with `retry` true means the call lacked what its `message` names: run it again with that. On any other error, or no JSON object, the chain stops, with the `message` (or what it printed) as the halt reason. After a halt, or when the chain stops, go to step 5; otherwise go on with f, then with the `next` entry, or with step 5 when there is none.
   - f. **Report completion:** "Pipeline [{current}/{total}]: {code} complete ({brief summary of output})."

5. **Result contract**: write the pipeline result from the journal, from the skf-forger skill root:

   ```bash
   uv run scripts/pipeline-journal.py finish --journal "<journal>" --result-dir "{sidecar_path}" [--halt-reason '<reason>']
   ```

   Give `--halt-reason` the reason the chain stopped with when no `step` call recorded it. The call prints the pipeline's `pipeline_status`, its `halt_reason` and, after a halt, its `route`: the next action. If it prints no JSON object, or its `status` is not `ok`, say so in step 6: the chain's own outcome stands.

6. **Pipeline summary.** After all workflows complete (or on halt), present: completed workflows with key outputs; the failed/halted workflow (if any) with its halt reason; remaining unexecuted workflows; and a next-steps recommendation, which after a halt is step 5's `route`.

## Resume

When the user accepts the offer On Activation step 5 made, run the chain from its journal instead of a new invocation: steps 1 and 2 are skipped, since the journal holds the plan the first parse produced. When the offer has a `user_action`, first confirm the user did it. Then, from the skf-forger skill root:

```bash
uv run scripts/pipeline-journal.py reopen --journal "<journal>"
```

`<journal>` is the path the offer named. The call prints the plan entries still to `run`, the `next` entry, the first of them, with its `inputs`, the `alias`, the first workflow's `args` and the handoff `data`. If it prints no JSON object, or its `status` is not `ok`, HALT with what it printed. Otherwise go on with step 3, then step 4 from that `next` entry, without step 4's `start` call (every `step` call names this `journal`): `{pipeline_alias}` is `alias`, and each entry runs with its `inputs`, as the `next` entry prints them.

## Special behaviors

- **`SF` in a sequence:** SF writes no result file; the one `SKF_SETUP_RESULT_JSON` envelope line it displays is its output. Continue on `status` `success`. Any other status halts the pipeline, with that status and any `error.reason` as the halt reason; so does a run that displays no envelope line, with the line it did display as the reason, or `no-result` when it displayed none.

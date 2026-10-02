<!-- Config: communicate in {communication_language}. -->

# Campaign Contracts

The self-contained contracts consulted at a specific moment: when a step HALTs, writes state or the decision log, or emits a headless progress event. Each stands alone so it survives context compaction.

## Exit Codes

Every HARD HALT exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                   |
| ---- | -------------------- | ----------------------------------------------------------- |
| 0    | success              | step-11 (terminal: the success line, which the health check displays last); step-resume §3 (campaign already complete: nothing to resume, and in headless mode the success line again). Never an error halt: no `emit-halt` |
| 2    | invalid-input        | step-01 §1 (no targets, or a target the parse script rejects: a malformed manifest line or brief target, a `repo_url` that is no GitHub repository, a name that is no skill name, a Tier A pin that is no X.Y.Z version, a duplicate name) and §2 (a quality gate the gate script rejects, a brief it cannot read, or a state file or backup that already exists); steps 02/03/04 §3 and step-06 §3 (a helper reports unreadable input or a required tool such as `gh` unavailable); step-05 §4 and §5, step-07 §2 and step-10 §3 (a directive override that breaks the quality gate, or a directive the gate script cannot read); step-05 §5 (the kickoff script cannot read its template, state, directive or a facts file, or a `file:` fact path names no file); step-resume §1/§3 (resume targets a missing campaign or unknown skill) |
| 3    | invalid-state        | any step §1 (`campaign-validate-state.py` non-zero on load), and any `campaign-state.py` write that exits 3 (the state, or the change, fails validation) |
| 4    | circular-deps        | step-02 §4 (a dependency cycle, a dangling `depends_on` reference, or a Tier A skill that depends on a Tier B skill: either way the plan cannot be followed) and §7 (`apply-plan` refuses the plan) |
| 5    | invalid-pin          | step-03 §4 and §5 (`apply-pins` refuses an invalid pin)      |
| 6    | inaccessible-repo    | step-04 §4 and §5 (`apply-provenance` refuses an inaccessible repo) |
| 7    | dependency-deadlock  | step-05 §4 (no skill ready and no recovery chosen; defensive, since Strategy rejects every order the loop cannot follow) |
| 8    | missing-brief        | step-03/04/05 §2, step-05 §4 and §5, step-06 §3 (brief missing/unreadable, or a skill has no matching brief target), and step-resume §3 (Setup stopped before it wrote the brief) |
| 9    | corrupt-state        | step-resume §1 (primary unrecoverable, `.bak` also invalid) |
| 10   | report-failure       | step-11 §2 — **degraded only**: the report could not be generated; the campaign still completes and state stays intact (never a hard halt that discards a finished campaign) |
| 11   | export-cancelled     | step-10 §4 (operator chose `[C]ancel` — graceful, resumable) |
| 12   | user-cancelled       | any interactive gate (operator typed `cancel` / `exit` / `:q` at a prompt between Setup and the Export gate — graceful, resumable) |
| 13   | dependency-blocked   | step-05 §4 (`[H]alt` at a skill whose dependency has not completed: the operator's choice, or the headless default while a dependency is still pending or active; graceful, resumable) |

## Result Contract on HARD HALT

`shared/scripts/schemas/skf-campaign-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) is the one definition of the `SKF_CAMPAIGN_RESULT_JSON` envelope, and the shared emitter, `{emitEnvelopeHelper}`, is the only thing that prints it. That helper is `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` when installed, `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` during development. Exit code 0 is never an error halt: step-11 builds the success line, and step-resume prints it again for a campaign already complete. Every HARD HALT in headless mode emits the error variant, so automators don't silently break:

```bash
uv run scripts/campaign-state.py halt-payload --state-file {campaignWorkspacePath}/_campaign-state.yaml --phase <step slug> --halt-reason <class> <<'SKF_CAMPAIGN_HALT' | uv run {emitEnvelopeHelper} emit-halt --workflow skf-campaign --target stderr
<the halt message>
SKF_CAMPAIGN_HALT
```

`<class>` is the Exit Codes meaning (e.g. `circular-deps`, `inaccessible-repo`), from which the emitter derives `exit_code`; `<step slug>` is the kebab portion of the step file where the HALT occurred. `halt-payload` adds the `completed` and `failed` counts of the state (0 before Setup wrote it) and the decision log (null before the campaign workspace exists). The emitter prints one line on stderr, with `status` `error`, `exit_code`, `halt_reason`, `phase` and an `error` object holding `code` and `message`. If either command exits non-zero, display the halt message alone.

## State Contract

Every write to `_campaign-state.yaml` goes through `scripts/campaign-state.py`. Each write reads the state and validates it (an invalid state is never rotated into `.bak`, and nothing is written), applies the operation, stamps `campaign.last_updated` (and any `started_at` or `completed_at` the operation sets) from the clock in UTC, validates the result (a change that would make the state invalid is refused), copies the valid primary it read to `_campaign-state.yaml.bak`, and writes the new state to a temporary file renamed over the old one. A crash therefore leaves the old file or the new one, never half of one, and `.bak` always holds the last valid state. `--stage N` on a write also sets `campaign.current_stage`: each stage writes its number only in its final write, after every gate, because resume starts at `current_stage + 1`.

| Operation | Step | What it writes |
| --- | --- | --- |
| `init` | step-01 | the state, from `campaign-parse-manifest.py`'s targets and the gate `campaign-quality-gate.py check` settles; refuses a state or backup that exists |
| `apply-plan` | step-02 | `dependency_graph` from `campaign-deps.py --compute` |
| `apply-pins` | step-03 | each resolved pin, from `campaign-validate-pins.py`'s output |
| `apply-provenance` | step-04 | each `commit_sha`, from `campaign-provenance.py`'s output |
| `set-skill` | step-05, step-resume | a skill's `status`, `quality_score`, `skill_path` or `brief_path`; `active` stamps `started_at` once, `completed` stamps `completed_at`, `pending` clears both |
| `append-workarounds` | step-05 | entries of a skill's `workarounds_applied`, each once |
| `apply-batch` | step-06 | the Tier B batch from its line-to-skill map: `--start`, `--results-file` or `--no-results` |
| `set-campaign` | steps 07 to 09 | `architecture_doc_path`, and the capstone, verification or refinement summary read from the sub-skill's envelope line (`capstone.verified` with the verification) |
| `set-stage` | steps 05, 10, 11 | `current_stage` alone |
| `recover` | step-resume | `.bak` over the primary, when `.bak` validates (exit 9 otherwise) |
| `archive` | SKILL.md (overwrite) | nothing: it moves the state, its `.bak` and the brief into a new folder under `archive/` and returns it |
| `resume` | step-resume | nothing: it returns the stage and step file to resume |
| `halt-payload` | any HARD HALT | nothing: it prints the error envelope's payload (Result Contract above) |

Its exit codes are the campaign's: 2 for invalid input (an unknown skill, an input file it cannot read, a script output that holds an error), 3 for an invalid state or change, 4 for a plan `apply-plan` refuses, 5 for a pin `apply-pins` refuses, 6 for a repository `apply-provenance` refuses, 9 for a `recover` with no valid backup. HALT with the same code.

## Decision Log

`_campaign-decision-log.md` is append-only, one typed and timestamped line per entry, written with `uv run scripts/campaign-state.py log --log-file {campaignWorkspacePath}/_campaign-decision-log.md --type <decision|auto|event> --text '<entry>'` (single-quote the entry, so the shell expands no `$` or backtick in it, and write an apostrophe inside it as `'\''`). Its types:

- `decision`: the operator's choice at a gate (skip or force, overwrite, export or cancel, re-run or next, a cancel)
- `auto`: the default a headless run took at a gate
- `event`: what happened without a choice: a failed skill and why, a skip the directive or a dependency forced, a recovery from the backup, a report or hook failure

## Headless Progress Events

When `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry, exit, and HARD HALT, so schedulers stream live progress instead of post-mortem-parsing the final envelope:

- entry: `{"stage":N,"name":"<slug>","status":"start"}`
- exit (just before chaining): `{"stage":N,"name":"<slug>","status":"done"}`
- on HARD HALT: `{"stage":N,"name":"<slug>","status":"halt","exit":<code>}` instead of `"done"`

`N` is the 0-indexed stage number (0 to 10) and `<slug>` is the kebab portion of the step filename. For the non-numbered routing/terminal steps (`resume`, `health-check`) emit `"stage":null` with the slug. One line per event; do not pretty-print.

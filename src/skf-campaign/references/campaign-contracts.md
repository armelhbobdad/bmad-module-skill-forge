<!-- Config: communicate in {communication_language}. -->

# Campaign Contracts

The self-contained contracts consulted at a specific moment: when a step HALTs, writes state or the decision log, or emits a headless progress event. Each stands alone so it survives context compaction.

## Exit Codes

Every HARD HALT exits with one of these codes:

| Code | Meaning             | Note                                                                   |
| ---- | ------------------- | ---------------------------------------------------------------------- |
| 0    | success             | Never an error halt: no `emit-halt`                                    |
| 2    | invalid-input       |                                                                        |
| 3    | invalid-state       |                                                                        |
| 4    | circular-deps       |                                                                        |
| 5    | invalid-pin         |                                                                        |
| 6    | inaccessible-repo   |                                                                        |
| 7    | dependency-deadlock | defensive: only a hand-edited state reaches it                         |
| 8    | missing-brief       |                                                                        |
| 9    | corrupt-state       |                                                                        |
| 10   | report-failure      | **degraded only**: the campaign still completes and state stays intact |
| 11   | export-cancelled    | graceful, resumable                                                    |
| 12   | user-cancelled      | graceful, resumable                                                    |
| 13   | dependency-blocked  | graceful, resumable                                                    |

## Result Contract on HARD HALT

`shared/scripts/schemas/skf-campaign-result-envelope.v1.json` (in the SKF module: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) is the one definition of the `SKF_CAMPAIGN_RESULT_JSON` envelope, and the shared emitter, `{emitEnvelopeHelper}`, is the only thing that prints it. That helper is `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` when installed, `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` during development. Exit code 0 is never an error halt: step-11 builds the success line, and step-resume prints it again for a campaign already complete. Every HARD HALT in headless mode emits the error variant, so automators don't silently break:

```bash
uv run scripts/campaign-state.py halt-payload --state-file {campaignWorkspacePath}/_campaign-state.yaml --phase <step slug> --halt-reason <class> <<'SKF_CAMPAIGN_HALT' | uv run {emitEnvelopeHelper} emit-halt --workflow skf-campaign --target stderr
<the halt message>
SKF_CAMPAIGN_HALT
```

`<class>` is the Exit Codes meaning (e.g. `circular-deps`, `inaccessible-repo`), from which the emitter derives `exit_code`; `<step slug>` is the kebab portion of the step file where the HALT occurred. `halt-payload` adds the `completed` and `failed` counts of the state (0 before Setup wrote it) and the decision log (null before the campaign workspace exists). The emitter prints one line on stderr, with `status` `error`, `exit_code`, `halt_reason`, `phase` and an `error` object holding `code` and `message`. If either command exits non-zero, display the halt message alone.

A caller reads the run's own `SKF_CAMPAIGN_RESULT_JSON` line, at the end or at a HARD HALT. A run that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result. Campaign writes no result file of its own, so nothing stands in for the line; its state stays on disk for `@Ferris campaign resume`.

## State Contract

Every write to `_campaign-state.yaml` goes through `scripts/campaign-state.py`. Each write reads the state and validates it (an invalid state is never rotated into `.bak`, and nothing is written), applies the operation, stamps `campaign.last_updated` (and any `started_at` or `completed_at` the operation sets) from the clock in UTC, validates the result (a change that would make the state invalid is refused), copies the valid primary it read to `_campaign-state.yaml.bak`, and writes the new state to a temporary file renamed over the old one. A crash therefore leaves the old file or the new one, never half of one, and `.bak` always holds the last valid state. `--stage N` on a write also sets `campaign.current_stage`: each stage writes its number only in its final write, after every gate, because resume starts at `current_stage + 1`.

| Operation | Step | What it writes |
| --- | --- | --- |
| `init` | step-01 | the state, from `campaign-parse-manifest.py`'s targets and the gate `campaign-quality-gate.py check` settles, then `campaign-brief.yaml` from the same targets (`--brief-out`); refuses a state or backup that exists |
| `apply-plan` | step-02 | `dependency_graph` from `campaign-deps.py --compute` |
| `apply-pins` | step-03 | each resolved pin, from `campaign-validate-pins.py`'s output |
| `apply-provenance` | step-04 | each `commit_sha`, from `campaign-provenance.py`'s output |
| `set-skill` | step-05, step-10, step-resume | a skill's `status`, `quality_score`, `skill_path`, `brief_path` or `export` outcome (`--export`); `active` stamps `started_at` once, `completed` stamps `completed_at`, `pending` clears both and the `export` outcome |
| `append-workarounds` | step-05 | entries of a skill's `workarounds_applied`, each once: the `--entry` texts, or with `--doc-rot-file` one `[doc-rot] {affected}: {candidate_category}` entry per correction create-skill's step 5c kept (no file, no entry) |
| `apply-batch` | step-06 | the Tier B batch from its line-to-skill map: `--start`, `--results-file` or `--no-results` |
| `set-campaign` | steps 07 to 09 | `architecture_doc_path`, and the capstone, verification or refinement summary read from the sub-skill's envelope line (`capstone.verified` with the verification); null for a stage skipped on purpose (`--no-<field>`), a sub-skill that printed no line (`--no-result <field>`, a `not_recorded` row with halt reason `no-result`) or a line it cannot read (one that does not parse, or has no `status` or `exit_code`: a `not_recorded` row with halt reason `result-unreadable`, exit 0); and `stage_outcomes`, each stage `completed`, `skipped` or `failed` with its halt reason and exit code |
| `set-stage` | steps 05, 10, 11 | `current_stage` alone |
| `recover` | step-resume | `.bak` over the primary, when `.bak` validates (exit 9 otherwise) |
| `archive` | step-01 §0 (overwrite) | nothing: it moves the state, its `.bak` and the brief into a new folder under `archive/` and returns it |
| `resume` | step-resume | nothing: it returns the stage and step file to resume |
| `halt-payload` | any HARD HALT | nothing: it prints the error envelope's payload (Result Contract above) |

Its exit codes are the campaign's: 2 for invalid input (an unknown skill, an input file it cannot read, a script output that holds an error), 3 for an invalid state or change, 4 for a plan `apply-plan` refuses, 5 for a pin `apply-pins` refuses, 6 for a repository `apply-provenance` refuses, 9 for a `recover` with no valid backup. HALT with the same code.

## Decision Log

`_campaign-decision-log.md` is append-only, one typed and timestamped line per entry, written with `uv run scripts/campaign-state.py log --log-file {campaignWorkspacePath}/_campaign-decision-log.md --type <decision|auto|event> --text '<entry>'` (single-quote the entry, so the shell expands no `$` or backtick in it, and write an apostrophe inside it as `'\''`). With `--once` it appends nothing when the log already holds a line of the same type and text, and returns `skipped` `true`, so a notice several calls report is logged once. Its types:

- `decision`: the operator's choice at a gate (skip or force, overwrite, export or cancel, re-run or next, a cancel)
- `auto`: the default a headless run took at a gate
- `event`: what happened without a choice: a failed skill and why, a skip the directive or a dependency forced, a recovery from the backup, a report or hook failure

## Headless Progress Events

When `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry, exit, and HARD HALT, so schedulers stream live progress instead of post-mortem-parsing the final envelope:

- entry: `{"stage":N,"name":"<slug>","status":"start"}`
- exit (just before chaining): `{"stage":N,"name":"<slug>","status":"done"}`
- on HARD HALT: `{"stage":N,"name":"<slug>","status":"halt","exit":<code>}` instead of `"done"`

`N` is the 0-indexed stage number (0 to 10) and `<slug>` is the kebab portion of the step filename. For the non-numbered routing/terminal steps (`resume`, `health-check`), and for a HARD HALT in SKILL.md On Activation (slug `activation`), emit `"stage":null` with the slug. One line per event; do not pretty-print.

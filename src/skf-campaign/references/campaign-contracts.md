<!-- Config: communicate in {communication_language}. -->

# Campaign Contracts

The self-contained contracts consulted at a specific moment — when a step HALTs, mutates state, or emits the final headless envelope. Each stands alone so it survives context compaction.

## Exit Codes

Every HARD HALT exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                   |
| ---- | -------------------- | ----------------------------------------------------------- |
| 0    | success              | step-11 (terminal); step-resume §3–§4 (campaign already complete — nothing to resume) |
| 2    | invalid-input        | step-01 §1 (no targets, or a target the parse script rejects: a malformed manifest line or brief target, a `repo_url` that is no GitHub repository, a name that is no skill name, a Tier A pin that is no X.Y.Z version, a duplicate name) and §2 (a quality gate the gate script rejects, or a brief it cannot read); steps 02/03/04 §4 and step-06 §3 (a helper reports unreadable input or a required tool such as `gh` unavailable); step-05 §4 and §5, step-07 §2 and step-10 §3 (a directive override that breaks the quality gate, or a directive the gate script cannot read); step-05 §5 (the kickoff script cannot read its template, state, directive or a facts file, or a `file:` fact path names no file); step-resume §1/§3 (resume targets a missing campaign or unknown skill) |
| 3    | invalid-state        | any step §1 (`campaign-validate-state.py` non-zero on load) |
| 4    | circular-deps        | step-02 §5 (a dependency cycle, a dangling `depends_on` reference, or a Tier A skill that depends on a Tier B skill: either way the plan cannot be followed) |
| 5    | invalid-pin          | step-03 §5                                                  |
| 6    | inaccessible-repo    | step-04 §5                                                  |
| 7    | dependency-deadlock  | step-05 §4 (no skill ready and no recovery chosen; defensive, since Strategy rejects every order the loop cannot follow) |
| 8    | missing-brief        | step-03/04/05 §2, step-05 §4 and §5, and step-06 §3 (brief missing/unreadable, or a skill has no matching brief target) |
| 9    | corrupt-state        | step-resume §1 (primary unrecoverable, `.bak` also invalid) |
| 10   | report-failure       | step-11 §2 — **degraded only**: the report could not be generated; the campaign still completes and state stays intact (never a hard halt that discards a finished campaign) |
| 11   | export-cancelled     | step-10 §4 (operator chose `[C]ancel` — graceful, resumable) |
| 12   | user-cancelled       | any interactive gate (operator typed `cancel` / `exit` / `:q` at a prompt between Setup and the Export gate — graceful, resumable) |
| 13   | dependency-blocked   | step-05 §4 (`[H]alt` at a skill whose dependency has not completed: the operator's choice, or the headless default while a dependency is still pending or active; graceful, resumable) |

## Result Contract on HARD HALT

In addition to the success-variant envelope (see Campaign Headless Envelope below), every HARD HALT emits an **error variant** so automators don't silently break. Emit one line on **stderr**:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"error","exit_code":<N>,"phase":"<slug>","error":{"code":"<class>","message":"<short>"},"skills_completed":N,"skills_failed":N,"campaign_report_path":null,"decision_log":"<path-or-null>"}
```

`<class>` is the Exit Codes meaning (e.g. `circular-deps`, `inaccessible-repo`); `<slug>` is the step where the HALT occurred. One line, no pretty-print.

## State Contract

All state mutations follow the read-backup-modify-write pattern:

1. **Read** `_campaign-state.yaml`
2. **Validate** via `uv run scripts/campaign-validate-state.py --state-file {stateFile}` (halt on invalid)
3. **Backup** — copy current `_campaign-state.yaml` to `_campaign-state.yaml.bak`
4. **Modify** in memory
5. **Update** `campaign.last_updated` to current ISO-8601 timestamp
6. **Write** modified state back to `_campaign-state.yaml`

The `.bak` file is one-deep (overwritten on every write). If the primary file is corrupted (crash during write), the `.bak` file contains the last valid state — step-resume §1 recovers from it automatically rather than dead-halting.

## Campaign Headless Envelope

When `{headless_mode}` is true, the final step emits a single-line JSON envelope on stdout:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"success|error","skills_completed":0,"skills_failed":0,"quality_scores":{},"export_verdicts":{},"skills_excluded":[],"campaign_report_path":"","decision_log":"","duration":""}
```

`status` is `"success"` when the campaign completes normally, `"error"` on any unrecoverable halt (with `exit_code` per the Exit Codes table: see Result Contract on HARD HALT above). `skills_completed` and `skills_failed` count per-skill outcomes. `quality_scores` maps skill names to their recorded scores: test-skill's for a Tier A skill, the skill-check score quick-skill records for a Tier B skill. `export_verdicts` maps each completed skill to its quality-gate verdict at Export (`pass`, `fallback` or `fail`), and `skills_excluded` lists the completed skills the gate kept from export (`fail`), so a completed skill is not taken for an exported one; both are `null` when the gate could not be applied. `campaign_report_path` points to the generated `campaign-report.md`. `decision_log` points to `_campaign-decision-log.md`. `duration` is the wall-clock time of the campaign run. Populate the counts, `quality_scores`, `export_verdicts`, `skills_excluded` and `duration` directly from the `campaign-report.py` result JSON (step-11 §2); do not recompute them by hand.

## Headless Progress Events

When `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry, exit, and HARD HALT, so schedulers stream live progress instead of post-mortem-parsing the final envelope:

- entry: `{"stage":N,"name":"<slug>","status":"start"}`
- exit (just before chaining): `{"stage":N,"name":"<slug>","status":"done"}`
- on HARD HALT: `{"stage":N,"name":"<slug>","status":"halt","exit":<code>}` instead of `"done"`

`N` is the 0-indexed stage number (0–10) and `<slug>` is the kebab portion of the step filename. For the non-numbered routing/terminal steps (`resume`, `health-check`) emit `"stage":null` with the slug. One line per event; do not pretty-print.

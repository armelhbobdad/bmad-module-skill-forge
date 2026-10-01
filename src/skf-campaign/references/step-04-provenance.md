---
nextStepFile: 'step-05-skill-loop.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
provenanceResultsFile: '{campaignWorkspacePath}/_provenance-results.json'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
provenanceScript: 'scripts/campaign-provenance.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Provenance

## STEP GOAL:

Verify that all target repositories are accessible and record the exact commit SHA for each target, establishing the provenance baseline for the campaign.

## RULES

- Write `campaign.current_stage` = 3 only in this stage's final state write, after every gate: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- Any inaccessible repo halts the campaign: all targets must be reachable before skill processing begins. The brief holds each `repo_url` (the state schema has no place for it).
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Brief

Load `{briefFile}` only to confirm it parses (the provenance script reads it directly). HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3: Verify Repo Access + Record Commit SHAs

Run the deterministic provenance check, keeping its JSON output in `{provenanceResultsFile}` for §5; do not parse repo URLs or call `gh` by hand:

```
uv run {provenanceScript} --state-file {stateFile} --brief-file {briefFile} > {provenanceResultsFile}
```

It writes `results[]`, one per skill with its `commit_sha` (of the skill's `pin`, else the default branch), `status`, `error` and `error_class` (`unauthenticated`, `not-found`, `rate-limited`, `forbidden`, `network`, or `other` for a target it could not look up), plus `all_accessible`, `inaccessible_count` and `systemic_hint`. Exit 0 = all accessible, 1 = one or more inaccessible, 2 = error (missing files, bad YAML, `gh` not installed). On script exit 2, HALT (exit code 2, `invalid-input`) surfacing the error: repo access cannot be verified without `gh`.

### §4: Handle Inaccessible Repos

If `all_accessible` is `false` (script exit 1), HALT (exit code 6, `inaccessible-repo`) and list each inaccessible repo with its URL, its `error_class` and its `error`. When the script returns a non-null `systemic_hint` (every target failed the same way: unauthenticated `gh`, no network, a rate limit, an organization's SSO policy), show that root-cause line first, above the per-repo errors, never in their place. Do NOT partially proceed: all repos must be verified before writing state.

### §5: Write State

Write every commit SHA and the stage in one write:

```
uv run {stateScript} apply-provenance --state-file {stateFile} --results-file {provenanceResultsFile} --stage 3
```

It sets each skill's `commit_sha` from `results[]` and refuses results that hold an inaccessible repo (exit 6, nothing written: HALT as in §4); on exit 3, HALT (exit code 3, `invalid-state`).

## OUTPUT

Display provenance summary: for each target, show name, repo URL, and recorded commit SHA. Chain to `{nextStepFile}`.

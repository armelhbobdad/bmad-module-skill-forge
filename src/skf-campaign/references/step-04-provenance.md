---
nextStepFile: 'step-05-skill-loop.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
provenanceScript: 'scripts/campaign-provenance.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Provenance

## STEP GOAL:

Verify that all target repositories are accessible and record the exact commit SHA for each target, establishing the provenance baseline for the campaign.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Reads the brief for `repo_url` (not in state — `repo_url` is NOT part of the state schema).
- Any inaccessible repo halts the campaign — all targets must be reachable before skill processing begins.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.current_stage` to `3`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Brief

Load `{briefFile}` only to confirm it parses (the provenance script reads it directly). HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §4 — Verify Repo Access + Record Commit SHAs

Run the deterministic provenance check — do not parse repo URLs or shell out to `gh` by hand:

```
uv run {provenanceScript} --state-file {stateFile} --brief-file {briefFile}
```

The script resolves `{owner}/{repo}` from each `repo_url` (tolerating `.git`/trailing slashes/SSH form), picks the ref (the skill's `pin`, else the repo default branch), runs `gh repo view` + `gh api commits`, and emits `results[]` with `commit_sha` and `status` per skill, plus `all_accessible`, `inaccessible_count`, and `systemic_hint`. Exit 0 = all accessible, 1 = one or more inaccessible, 2 = error (missing files, bad YAML, `gh` not installed).

### §5 — Handle Inaccessible Repos

If `all_accessible` is `false` (script exit 1), HALT (exit code 6, `inaccessible-repo`). When the script returns a non-null `systemic_hint` (every target failed the same way — e.g. unauthenticated `gh`, no network, rate limit), present that single root-cause line instead of a wall of near-identical per-repo errors. Otherwise list each inaccessible repo, its URL, and its error. Do NOT partially proceed — all repos must be verified before writing state.

### §6 — Write State

Set each skill's `commit_sha` from the script's `results[]`. Set `campaign.current_stage` to `3`. Set `campaign.last_updated` to current ISO-8601 with timezone. Write to `{stateFile}`.

## OUTPUT

Display provenance summary — for each target, show name, repo URL, and recorded commit SHA. Chain to `{nextStepFile}`.

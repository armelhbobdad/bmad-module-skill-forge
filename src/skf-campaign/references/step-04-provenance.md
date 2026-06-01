---
nextStepFile: 'step-05-skill-loop.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
briefFile: 'forge-data/_campaign/campaign-brief.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Provenance

## STEP GOAL:

Verify that all target repositories are accessible and record the exact commit SHA for each target, establishing the provenance baseline for the campaign.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Reads the brief for `repo_url` (not in state — `repo_url` is NOT part of the state schema).
- Any inaccessible repo halts the campaign — all targets must be reachable before skill processing begins.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.current_stage` to `3`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Read Brief

Load `{briefFile}`. Build a lookup map from `targets[].name` to `targets[].repo_url`. HALT if the brief is missing or unreadable.

### §3 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §4 — Verify Repo Access + Record Commit SHAs

For each skill in state, look up its `repo_url` from the brief lookup map. For each target:

1. **Verify access** — run `gh repo view {repo_url} --json name`. If this fails, record the failure (repo name, attempted URL, error message) and continue to the next target.
2. **Determine ref** — if the skill has a `pin` (not null), use the pin as the ref. Otherwise, get the default branch via `gh repo view {repo_url} --json defaultBranchRef --jq .defaultBranchRef.name`.
3. **Get commit SHA** — extract `{owner}/{repo}` from the `repo_url` (handle trailing `.git` or trailing slashes). Run `gh api repos/{owner}/{repo}/commits/{ref} --jq .sha`.
4. **Write commit_sha** — store the retrieved SHA on the skill's entry in the in-memory state.

### §5 — Handle Inaccessible Repos

If ANY repo verification failed in §4, collect all failures and HALT with a clear error listing each inaccessible repo, the attempted URL, and the error. Do NOT partially proceed — all repos must be verified before writing state.

### §6 — Write State

Set each skill's `commit_sha` to the recorded SHA. Set `campaign.current_stage` to `3`. Set `campaign.last_updated` to current ISO-8601 with timezone. Write to `{stateFile}`.

## OUTPUT

Display provenance summary — for each target, show name, repo URL, and recorded commit SHA. Chain to `{nextStepFile}`.

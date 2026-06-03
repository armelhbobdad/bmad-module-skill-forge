---
nextStepFile: 'step-04-provenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
pinScript: 'scripts/campaign-validate-pins.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Pins

## STEP GOAL:

Validate all version pins against real releases/branches before the campaign proceeds, catching invalid pins early with actionable suggestions.

## RULES

- This step uses the **read-backup-modify-write** pattern (state file exists from step-01).
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.current_stage` to `2`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- HALT (exit code 5, `invalid-pin`) on any invalid pin — invalid pins are errors, not gates.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Brief

Load `{briefFile}`. Build a lookup map from `targets[].name` to `targets[].repo_url`. HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §4 — Validate Pins

Run `uv run {pinScript} --state-file {stateFile} --brief-file {briefFile}`. Parse the JSON output. For each result: if `status` is `"valid"` or `"resolved"`, the pin is good; if `"invalid"`, collect the failure with suggestions.

### §5 — Handle Invalid Pins

If ANY pins are invalid, collect ALL failures first (all-or-nothing pattern), then HALT (exit code 5, `invalid-pin`) with a clear error listing each invalid pin, the skill name, the attempted pin value, and suggested corrections. Do NOT partially proceed.

### §6 — Update State

For each skill where validation returned `status: "resolved"` (pin was null, latest release found), update `skill.pin` to the `resolved_ref` value. For `status: "valid"` where the input pin differs from `resolved_ref` (e.g., user said `2.0.0` but the actual tag is `v2.0.0`), update `skill.pin` to the `resolved_ref` so downstream steps use the exact ref name. Set `campaign.current_stage` to `2`. Set `campaign.last_updated`. Write to `{stateFile}`.

## OUTPUT

Display pin validation summary — for each skill: name, pin, resolved ref, ref type. Chain to `{nextStepFile}`.

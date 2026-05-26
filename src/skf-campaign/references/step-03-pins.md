---
nextStepFile: 'step-04-provenance.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
briefFile: 'forge-data/_campaign/campaign-brief.yaml'
pinScript: 'scripts/campaign-validate-pins.py'
---

<!-- Config: communicate in {communication_language}. -->

# Pins

## STEP GOAL:

Validate all version pins against real releases/branches before the campaign proceeds, catching invalid pins early with actionable suggestions.

## RULES

- This step uses the **read-backup-modify-write** pattern (state file exists from step-01).
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.current_stage` to `2`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone.
- HALT on any invalid pin — invalid pins are errors, not gates.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Read Brief

Load `{briefFile}`. Build a lookup map from `targets[].name` to `targets[].repo_url`. HALT if the brief is missing or unreadable.

### §3 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §4 — Validate Pins

Run `uv run python {pinScript} --state-file {stateFile} --brief-file {briefFile}`. Parse the JSON output. For each result: if `status` is `"valid"` or `"resolved"`, the pin is good; if `"invalid"`, collect the failure with suggestions.

### §5 — Handle Invalid Pins

If ANY pins are invalid, collect ALL failures first (all-or-nothing pattern), then HALT with a clear error listing each invalid pin, the skill name, the attempted pin value, and suggested corrections. Do NOT partially proceed.

### §6 — Update State

For each skill where validation returned `status: "resolved"` (pin was null, latest release found), update `skill.pin` to the `resolved_ref` value. For `status: "valid"` where the input pin differs from `resolved_ref` (e.g., user said `2.0.0` but the actual tag is `v2.0.0`), update `skill.pin` to the `resolved_ref` so downstream steps use the exact ref name. Set `campaign.current_stage` to `2`. Set `campaign.last_updated`. Write to `{stateFile}`.

## OUTPUT

Display pin validation summary — for each skill: name, pin, resolved ref, ref type. Chain to `{nextStepFile}`.

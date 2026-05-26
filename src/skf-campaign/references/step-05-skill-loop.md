---
nextStepFile: 'step-06-batch.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
briefFile: 'forge-data/_campaign/campaign-brief.yaml'
depsScript: 'scripts/campaign-deps.py'
kickoffTemplate: 'templates/kickoff-template.md'
---

<!-- Config: communicate in {communication_language}. -->

# Skill Loop

## STEP GOAL:

Iterate skills in `dependency_graph.execution_order`, processing each Tier A skill through the full pipeline while enforcing dependency gates. Write state after each skill completes to survive context death between skills.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.current_stage` to `4`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Write state after EACH skill completes (not just at end) — context death between skills must be survivable.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. Dependency gate blocks default to HALT (safest — never silently skip dependencies).

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Read Brief

Load `{briefFile}`. Build a lookup map from `targets[].name` to `targets[].repo_url`. HALT if the brief is missing or unreadable.

### §3 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path. Apply directive contents as campaign-wide context for all skill processing. If the file is not found, continue without error (directive is optional).

### §4 — Dependency Gate Check

For each skill in `dependency_graph.execution_order`, before processing:

1. Skip Tier B skills — they are processed in step-06 via batch mode.
2. Skip skills whose status is already `"completed"`, `"failed"`, or `"skipped"` (resume support).
3. Run `uv run python {depsScript} --check --state-file {stateFile} --skill {skill_name}`.
4. If `ready: true` — proceed to §5 for this skill.
5. If `ready: false` — present the blocked skill and its unmet dependencies:
   - `[S]kip` — mark skill as `"skipped"`, backup and write state, continue to next skill.
   - `[F]orce` — re-run with `--force`, proceed to §5 despite unmet deps.
   - `[H]alt` — stop the campaign loop. (Default in headless mode.)
6. **Deadlock detection:** after iterating through all remaining skills and finding none ready, HALT with a clear message listing the blocked skills and their unmet dependencies.

### §5 — Per-Skill Processing

For each ready Tier A skill:

1. **Activate** — set `status` to `"active"`, set `started_at` to current ISO-8601 with timezone. Backup and write state.
2. **Execute pipeline:**
   - Pre-apply (`skf-preapply.py` via campaign wrapper) — apply known workarounds.
   - Kickoff emit — generate fresh-context handoff from `{kickoffTemplate}`.
   - AN → BS → CS → TS — standard forge pipeline for this skill.
3. **Record results:**
   - On success: set `status` to `"completed"`, set `completed_at` to current ISO-8601 with timezone, record `quality_score`. Backup and write state.
   - On failure: set `status` to `"failed"`. Backup and write state.

### §6 — Propagate Findings

After each completed skill, propagate quality findings and doc-rot corrections to campaign-level tracking (`workarounds_applied`, `quality_score`).

### §7 — Loop Completion

When all Tier A skills in `execution_order` are processed (completed, failed, or skipped):

1. Set `campaign.current_stage` to `4`.
2. Set `campaign.last_updated` to current ISO-8601 with timezone.
3. Backup and write state.

## OUTPUT

Display per-skill summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.

---
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
---

<!-- Config: communicate in {communication_language}. -->

# Resume

## STEP GOAL:

Validate campaign state integrity, determine the resume point, and chain to the appropriate stage step file. This is a read-only routing step — it does not modify state.

## RULES

- This step is **read-only** — it does NOT modify `{stateFile}` or create a backup. No read-backup-modify-write pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- The chain target is determined dynamically from state — there is no fixed `nextStepFile`.
- All warnings from backup consistency checks are advisory — the primary file is authoritative.
- If `{headless_mode}` is true, auto-proceed through any confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. If the file does not exist, HALT: "No campaign state found. Run `campaign` to start a new campaign."

If the file is empty or contains corrupt YAML, HALT with the parse error.

Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Backup Consistency Check

Check if `{backupFile}` exists.

**If `.bak` does not exist:** warn "No backup file found — campaign may have been created but never modified." Continue.

**If `.bak` exists:**

1. Attempt to parse as YAML. If corrupt, warn: "Backup file is corrupt YAML — cannot verify consistency." Continue.
2. Validate against `{stateSchemaFile}`. If invalid, warn: "Backup file fails schema validation." Continue.
3. Compare primary vs backup:
   - If `primary.campaign.last_updated < backup.campaign.last_updated`, warn: "Primary appears older than backup — possible crash during last write. Consider recovering from .bak."
   - If `primary.campaign.current_stage < backup.campaign.current_stage`, warn: "Primary stage is behind backup stage — possible crash during last write. Consider recovering from .bak."

All warnings are advisory — the primary file is authoritative for resume decisions.

### §3 — Determine Resume Point

Two paths based on whether `--from=<skill>` was provided in the invocation:

**With `--from=<skill>`:**

1. Find the named skill in `skills[]` by `name`.
2. If not found → HALT: "Unknown skill '{name}'. Known skills: {comma-separated list of all skill names from state}."
3. If the skill's `status` is `"completed"`, `"failed"`, or `"skipped"`:
   - Warn: "Skill '{name}' is already {status}."
   - Find the next skill in `dependency_graph.execution_order` after the named one whose `status` is `"pending"` or `"active"`.
   - If none found → HALT: "All remaining skills are complete. Run `campaign` to start a new campaign."
   - Use that next pending/active skill as the resume target.
4. If an active skill already exists in `skills[]` AND it is a different skill from the `--from` target, warn: "Skill '{active_name}' is currently active — honoring explicit --from override."
5. Determine the target step file:
   - Tier A skill with status `"pending"` or `"active"` → stage 4 (`step-05-skill-loop.md`)
   - Tier B skill with status `"pending"` or `"active"` → stage 5 (`step-06-batch.md`)

**Without `--from`:**

1. Scan `skills[]` for any skill with `status == "active"`.
   - If found and `tier == "A"` → resume target is stage 4 (`step-05-skill-loop.md`). The skill loop's §4 will skip completed skills until it reaches the active one.
   - If found and `tier == "B"` → resume target is stage 5 (`step-06-batch.md`). The batch step processes Tier B skills.
2. If no active skill → use `campaign.current_stage` from state.
3. Map `current_stage` to the corresponding step file using the stage table in §4.

### §4 — Resume Routing

Map `current_stage` to step file:

| Stage | Step File |
|-------|-----------|
| 0 | step-01-setup.md |
| 1 | step-02-strategy.md |
| 2 | step-03-pins.md |
| 3 | step-04-provenance.md |
| 4 | step-05-skill-loop.md |
| 5 | step-06-batch.md |
| 6 | step-07-capstone.md |
| 7 | step-08-verify.md |
| 8 | step-09-refine.md |
| 9 | step-10-export.md |
| 10 | step-11-maintenance.md |

Display a resume summary before chaining:

```
CAMPAIGN RESUME: {campaign.name}

  Resuming from: Stage {stage_number} — {stage_name}
  Target skill:  {skill_name} (if --from was used, otherwise "auto-detected" or "N/A")
  Skills completed: {completed_count} / {total_count}
  Skills remaining: {pending_count} pending, {active_count} active, {failed_count} failed, {skipped_count} skipped
  Last updated:  {campaign.last_updated}
```

If `campaign.current_stage` is `10` and all skills have status `"completed"`, `"failed"`, or `"skipped"`:
HALT: "Campaign has reached its final stage. All skills have been processed."

## OUTPUT

Chain to the determined step file.

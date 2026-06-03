---
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Resume

## STEP GOAL:

Validate campaign state integrity, determine the resume point, and chain to the appropriate stage step file. This is a read-only routing step — it does not modify state.

## RULES

- This step is **read-only by default** — it does NOT modify `{stateFile}` except in the one recovery case below (restoring a valid `.bak` over a corrupt primary), which is the State Contract's advertised safety net.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; the recovery path in §1 governs what happens on failure.
- The chain target is determined dynamically from state — there is no fixed `nextStepFile`.
- If `{headless_mode}` is true, auto-proceed through any confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State (with `.bak` recovery)

Load `{stateFile}`. If the file does not exist, HALT: "No campaign state found. Run `campaign` to start a new campaign."

Run `uv run {validateScript} --state-file {stateFile}`. If it succeeds (exit 0), proceed to §2.

If it fails (primary missing/corrupt YAML/schema-invalid), **attempt automatic recovery from the backup** rather than dead-halting — this is exactly the crash-during-write case the State Contract promises `.bak` covers:

1. If `{backupFile}` exists, run `uv run {validateScript} --state-file {backupFile}`.
2. If the backup is valid: copy `{backupFile}` over `{stateFile}`, log to the decision log "primary corrupt — recovered from backup as of {bak.last_updated}", inform the operator, and continue with the recovered state.
3. If the backup is missing or also invalid: HALT with exit code 9 (`corrupt-state`), reporting both the primary and backup validation errors so the operator knows neither is usable.

### §2 — Backup Consistency Check

Check if `{backupFile}` exists.

**If `.bak` does not exist:** warn "No backup file found — campaign may have been created but never modified." Continue.

**If `.bak` exists** (and §1 did not already recover from it):

1. Run `uv run {validateScript} --state-file {backupFile}`. If invalid, warn: "Backup file fails validation — cannot use for recovery." Continue with the primary.
2. Compare primary vs backup. If `primary.campaign.last_updated < backup.campaign.last_updated` OR `primary.campaign.current_stage < backup.campaign.current_stage`, the primary looks behind the backup (possible crash during last write). Present a recovery choice:
   - `[R]ecover` — copy `{backupFile}` over `{stateFile}` and resume from the backup's state.
   - `[K]eep` — keep the primary as authoritative (the default).

   In headless mode, default to `[K]eep` and log the auto-decision (a behind-backup primary may be intentional; never silently overwrite without a clear corruption signal — that case is handled in §1). Otherwise the primary is authoritative.

### §3 — Determine Resume Point

Two paths based on whether `--from=<skill>` was provided in the invocation:

**With `--from=<skill>`:**

1. Find the named skill in `skills[]` by `name`.
2. If not found → HALT: "Unknown skill '{name}'. Known skills: {comma-separated list of all skill names from state}."
3. If the skill's `status` is `"completed"`, `"failed"`, or `"skipped"`, the operator may have meant to re-run it (e.g. it passed with a low score) rather than skip past it. Present a choice:
   - `[R]e-run` — reset the named skill to `"pending"` and resume from its stage. (Read-only step caveat: this single status reset follows read-backup-modify-write — back up first.)
   - `[N]ext` — find the next skill in `dependency_graph.execution_order` after the named one whose `status` is `"pending"` or `"active"` and resume there. If none found → HALT: "All remaining skills are complete. Run `campaign` to start a new campaign."
   - `[H]alt` — stop without resuming.

   In headless mode, default to `[N]ext` and log the auto-decision. Log the chosen action to the decision log.
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

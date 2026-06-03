---
nextStepFile: 'step-03-pins.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
depsScript: 'scripts/campaign-deps.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Strategy

## STEP GOAL:

Compute the execution order from dependency edges, detect circular dependencies, and present a human-readable strategy view to the operator so the campaign plan is visible before execution begins.

## RULES

- This step uses the **read-backup-modify-write** pattern (state file exists from step-01).
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Write `execution_order` and `circular_deps_detected` to `dependency_graph`.
- Update `campaign.current_stage` to `1`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §3 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §4 — Compute Execution Order

Run the deterministic topological sort — do not hand-compute it:

```
uv run {depsScript} --compute --state-file {stateFile}
```

Parse the JSON output: `execution_order` (the ordered skill names — Kahn's sort with Tier A placed before Tier B within a dependency level), `circular_deps_detected` (bool), and `cycle_participants` (the unplaced skills when a cycle exists, else null). Exit code 1 from the script signals a cycle or a dangling dependency reference; exit code 2 signals a state/parse error — surface either and HALT.

### §5 — Handle Circular Dependencies

If `circular_deps_detected` is `true`, HALT (exit code 4, `circular-deps`) with a clear error listing `cycle_participants` and their mutual `depends_on` edges. Do NOT proceed — circular dependencies make execution order impossible.

### §6 — Write State

Set `dependency_graph.execution_order` to the computed order. Set `dependency_graph.circular_deps_detected` to the detection result. Set `campaign.current_stage` to `1`. Set `campaign.last_updated` to current ISO-8601 with timezone. Write to `{stateFile}`.

### §7 — Present Strategy View

Display a human-readable strategy summary to the operator (not written to a file — display only):

```
CAMPAIGN STRATEGY: {campaign_name}

EXECUTION ORDER:
  1. {skill_name} [Tier {tier}] {pin or "latest"}
  2. {skill_name} [Tier {tier}] {pin or "latest"} ← depends on: {dep1, dep2}
  ...

DEPENDENCY MAP:
  {skill_a} → {skill_b}, {skill_c}
  {skill_d} → (no dependencies)
  ...

QUALITY GATE:
  Hard gate: {quality_gate.hard}
  Soft target: {quality_gate.soft_target}%
  Soft fallback: {quality_gate.soft_fallback}%

TIER DISTRIBUTION:
  Tier A (full pipeline): {count}
  Tier B (QS batch): {count}
```

### §8 — Plan Confirmation Gate

The strategy view is the last review surface before a potentially long, mostly-unattended run begins. Present a confirmation gate:

- `[P]roceed` — begin execution (chain to `{nextStepFile}`).
- `[C]ancel` — stop now with exit code 12 (`user-cancelled`); state is intact and resumable. To change targets, edit the campaign brief (`{campaignWorkspacePath}/campaign-brief.yaml`) or re-run `campaign` (overwrite), then start again.

**HALT and wait for operator input.** In headless mode, auto-proceed with `[P]` and log "headless: auto-proceed past plan-confirmation gate" to the decision log.

## OUTPUT

Confirm strategy computed, display the strategy view, and resolve the §8 gate. Chain to `{nextStepFile}`.

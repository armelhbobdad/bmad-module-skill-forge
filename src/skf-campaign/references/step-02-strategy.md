---
nextStepFile: 'step-03-pins.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
depsScript: 'scripts/campaign-deps.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Strategy

## STEP GOAL:

Compute the execution order from dependency edges, detect circular dependencies, and present a human-readable strategy view to the operator so the campaign plan is visible before execution begins.

## RULES

- Write `campaign.current_stage` = 1 only in this stage's final state write, after every gate: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work. Here that write follows the §6 plan gate, so a campaign cancelled at the plan shows the plan again when it resumes.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, auto-proceed through the plan gate with its default action and log the auto-decision; emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3: Compute Execution Order

Run the deterministic topological sort; do not hand-compute it:

```
uv run {depsScript} --compute --state-file {stateFile}
```

Parse the JSON output: `execution_order` (the ordered skill names: Kahn's sort with Tier A placed before Tier B within a dependency level), `circular_deps_detected` (bool), `cycle_participants` (the unplaced skills when a cycle exists, else null), `tier_counts` (`{"A": n, "B": m}`, for the §5 strategy view) and `tier_inversions` (each Tier A `skill` that `depends_on` a Tier B skill). Script exit 1 signals a plan the stages cannot follow (a cycle, a dangling `depends_on` reference or a tier inversion), handled at §4 before the §5 view shows any order. Script exit 2 signals the helper could not read/parse the state file; HALT (exit code 2, `invalid-input`) surfacing its error.

### §4: Handle Unorderable Graph

If the graph cannot be followed (script exit 1), HALT (exit code 4, `circular-deps`): the execution order is impossible, so do not proceed. Three cases:

- **Cycle** (`circular_deps_detected: true`): list `cycle_participants` and their mutual `depends_on` edges.
- **Dangling reference** (a `DANGLING_DEPENDENCY` error with no `execution_order`): name the skill and the unknown dependency it references.
- **Tier A on Tier B** (`tier_inversions` non-empty, a `TIER_INVERSION` error): name each `skill` and the Tier B skill it `depends_on`. Tier B skills are built in the batch stage, after the skill loop, so the Tier A skill could never pass its dependency gate. Guidance: make the dependency Tier A, or drop the dependency, then re-run `campaign` and choose overwrite.

### §5: Present Strategy View

Display a human-readable strategy summary to the operator (display only: it is not written to a file):

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

Fill the TIER DISTRIBUTION counts from `tier_counts` in the §3 script output; do not re-tally `skills[]` by hand.

### §6: Plan Confirmation Gate

The strategy view is the last review surface before a potentially long, mostly-unattended run begins. Present a confirmation gate:

- `[P]roceed`: write the plan (§7), then chain to `{nextStepFile}`.
- `[C]ancel`: log the cancel, then stop with exit code 12 (`user-cancelled`). Nothing of this stage is written, so the state is intact and a resume shows this plan again. To change targets, tiers, pins or dependencies, re-run `campaign` and choose overwrite: they live in the state that Setup wrote, and editing `campaign-brief.yaml` does not reach them.

**HALT and wait for operator input.** In headless mode, auto-proceed with `[P]` and log "headless: auto-proceed past plan-confirmation gate" (type `auto`).

### §7: Write State

On `[P]roceed`, write the plan and the stage in one write:

```
uv run {stateScript} apply-plan --state-file {stateFile} --stage 1
```

It sets `dependency_graph.execution_order` and `circular_deps_detected` from the same `campaign-deps.py --compute` the §3 view came from, so the order on disk is the order shown. On exit 4 (the graph can no longer be followed: the state changed since §3), HALT (exit code 4, `circular-deps`) with its `errors[]`; on exit 3, HALT (exit code 3, `invalid-state`).

## OUTPUT

Confirm strategy computed, display the strategy view, resolve the §6 gate and write the §7 plan. Chain to `{nextStepFile}`.

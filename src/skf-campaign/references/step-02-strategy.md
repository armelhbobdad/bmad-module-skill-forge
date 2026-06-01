---
nextStepFile: 'step-03-pins.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
---

<!-- Config: communicate in {communication_language}. -->

# Strategy

## STEP GOAL:

Compute the execution order from dependency edges, detect circular dependencies, and present a human-readable strategy view to the operator so the campaign plan is visible before execution begins.

## RULES

- This step uses the **read-backup-modify-write** pattern (state file exists from step-01).
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Write `execution_order` and `circular_deps_detected` to `dependency_graph`.
- Update `campaign.current_stage` to `1`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Backup State

Copy `{stateFile}` to `{backupFile}` before any modification.

### §3 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path. Apply directive contents as campaign-wide context for this stage's processing. If the file is not found, continue without error (directive is optional).

### §4 — Compute Execution Order

Extract `skills[]` and their `depends_on` edges. Perform a topological sort (Kahn's algorithm):

1. Build an adjacency list from `skills[].depends_on` — for each skill, record which other skills depend on it.
2. Compute in-degrees for each skill (count of `depends_on` entries pointing to it).
3. Initialize a queue with all skills that have in-degree 0 (no dependencies).
4. While the queue is not empty:
   a. Dequeue a skill.
   b. Add it to the execution order.
   c. For each skill that depends on it, decrement that skill's in-degree.
   d. If any skill's in-degree reaches 0, enqueue it.
5. Within the same dependency level, place Tier A skills before Tier B (Tier A skills go through the full pipeline; Tier B skills are batched later in step-06).
6. If all skills are placed → valid execution order, set `circular_deps_detected` to `false`.
7. If any skills remain unplaced → circular dependency detected, set `circular_deps_detected` to `true`.

### §5 — Handle Circular Dependencies

If `circular_deps_detected` is `true`, HALT with a clear error listing the cycle — identify the unplaced skills and their mutual `depends_on` edges. Do NOT proceed — circular dependencies make execution order impossible.

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

## OUTPUT

Confirm strategy computed and display the strategy view to the operator. Chain to `{nextStepFile}`.

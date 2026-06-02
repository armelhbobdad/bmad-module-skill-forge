# Pipeline Contracts

## Overview

Pipelines chain multiple SKF workflows in sequence. The forger orchestrates the chain, passing data between workflows via filesystem artifacts and validating output contracts at each transition.

## Syntax

The forger recognizes pipeline invocations when the user provides multiple workflow codes:

```
AN CS TS EX              — space-separated codes
AN -> CS -> TS -> EX     — arrow-separated (equivalent)
BS CS[cocoindex] TS EX   — with target argument in brackets
CS TS[min:80] EX         — with circuit breaker threshold
```

The forger also accepts common pipeline aliases:

| Alias | Expands To | Description |
|-------|-----------|-------------|
| `forge-auto` | `AN[auto] BS[auto] CS TS[min:90] EX` | Zero-ceremony auto-compile pipeline (bare repo/doc URL → verified skill) |
| `forge` | `BS CS TS EX` | Full skill creation pipeline (brief through export) |
| `forge-quick` | `QS TS EX` | Quick skill pipeline |
| `maintain` | `AS US TS EX` | Maintenance cycle (audit → update → test → export) |

**Deprecated alias:** `deepwiki` resolves to `forge-auto` (renamed to avoid collision with the DeepWiki MCP — the pipeline auto-forges a verified skill and does not call that MCP). It still works but emits a one-time deprecation notice.

**Note:** `campaign` is a standalone workflow invoked via `@Ferris campaign`, not a pipeline alias. It orchestrates its own multi-stage pipeline internally with dependency tracking and resume.

## Pipeline Rules

1. **Left to right execution** — each workflow completes before the next begins
2. **Headless implied** — pipelines activate `{headless_mode}` automatically for all workflows in the chain (the user already committed to the sequence)
3. **Data forwarding** — the forger resolves output-to-input mapping between adjacent workflows (see Data Flow table)
4. **Circuit breakers** — if a workflow's output fails its quality check, the pipeline halts with a summary of what completed and what remains
5. **Error halts propagate** — if any workflow hard-halts, the pipeline stops immediately
6. **Progress reporting** — the forger reports completion of each workflow before starting the next

## Pipeline Arguments

Pipeline-level arguments (e.g., `--pin <version>`) are passed to the first workflow's data context. The workflow decides how to consume them. For the `forge-auto` pipeline, `--pin` flows to AN, where `step-auto-scope.md §0b` uses it for pin resolution.

## Data Flow

How outputs from one workflow become inputs to the next:

| From | To | Data Passed | How |
|------|-----|------------|-----|
| AN | BS | `brief_path` from generated brief | Forger passes the `brief_path` from AN's output to BS[auto], which loads and enriches the brief |
| AN | CS | `skill-brief.yaml` paths from generated briefs | Forger passes each `brief_path` written by AN to CS; in batch mode, CS processes all sequentially |
| BS | CS | `skill-brief.yaml` path | Forger passes the brief path written by BS as `brief_path` to CS |
| CS | TS | skill name (derived from brief) | Forger passes the `skill_name` from the completed CS to TS |
| CS | EX | skill name | Same — forger resolves the created skill's name |
| TS | EX | skill name + test result | Forger checks `result` field in test report; if FAIL and circuit breaker active, halts |
| QS | TS | skill name (from `repo_name`) | Forger passes the quick-skill's output name to TS |
| QS | EX | skill name | Same |
| AS | US | skill name + drift severity | Forger checks `summary.severity` in `audit-skill-result-latest.json`; if CLEAN, skips US |
| VS | RA | architecture doc path | Already known from VS invocation |

## Circuit Breakers

Circuit breakers halt the pipeline when a workflow's output doesn't meet a quality threshold:

| Workflow | Check | Default Threshold | Halt Condition |
|----------|-------|-------------------|----------------|
| AN | recommended units count | min: 1 | Zero skillable units found |
| CS | compilation success | must complete | Hard error during compilation |
| TS | completeness score | min: 60 (per-pipeline defaults apply — see init.md §1b) | Score below 80% floor (scores between 80% and per-pipeline threshold produce a fallback PASS with evidence report — pipeline continues) |
| AS | drift score | not CRITICAL | Critical drift found |
| VS | feasibility verdict | not BLOCKED | All integrations blocked |

Override syntax: `TS[min:80]` sets the test-skill threshold to 80 for this pipeline run.

### Bracket Syntax

Brackets after a workflow code (`CODE[value]`) are parsed as follows:

- **Circuit breaker override**: `min:N` where N is a number — e.g., `TS[min:80]` sets the threshold for that workflow
- **Mode flag**: `auto` — e.g., `AN[auto]` activates auto mode for that workflow. The workflow's first step reads the flag from pipeline data context and routes to the appropriate auto-mode step file.
- **Target argument**: any other value — e.g., `CS[cocoindex]` passes "cocoindex" as the target to CS

Only workflows with a circuit breaker entry (AN, CS, TS, AS, VS) accept `min:N` overrides. All other workflows ignore `min:N` brackets. Target arguments are valid for any workflow that accepts a named input (CS, QS, BS, US, etc.).

## Pipeline State

The forger tracks pipeline state in memory during execution:

```yaml
pipeline:
  alias: "forge"          # pipeline alias name, or null for ad-hoc sequences
  workflows: [AN, CS, TS, EX]
  current_index: 1
  completed:
    - {code: AN, status: ok, output: {units: 3, briefs: [...]}}
  pending: [CS, TS, EX]
  data:
    pipeline_alias: "forge" # forwarded to each workflow's data context (consumed by TS init.md §1b for per-pipeline threshold lookup)
    skill_name: "cocoindex"
    brief_path: "/path/to/skill-brief.yaml"
    target: "cocoindex"
```

## Anti-Patterns

The forger validates the pipeline sequence and warns about:

| Pattern | Issue | Suggestion |
|---------|-------|------------|
| EX before TS | Exporting untested skill | Add TS before EX |
| US without AS | Updating without audit | Run AS first to detect what changed |
| CS without BS or AN | Compiling without brief | Need a brief — use QS for quick path, or AN for brownfield |
| TS after EX | Testing after export | Move TS before EX |
| Duplicate codes | Same workflow twice | Remove duplicate |

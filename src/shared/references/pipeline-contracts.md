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

An alias takes its arguments after it, and they go, in order, to the inputs of the alias's first workflow: `forge-auto <repo-or-doc-url>` gives AN its `project_path`, `forge <repo-url-or-path> <skill-name>` gives BS its `target_repo` and `skill_name`, `forge-quick <package-or-url>` gives QS its `target`, and `maintain <skill>` gives AS its `skill_name`. The forger's `parse-pipeline.py` script binds them and returns them as `args`. A missing or left-over argument, a flag the pipeline does not take, or a `--pin` with no value stops the pipeline before any workflow runs.

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
| TS | EX | skill name + settled verdict | EX runs only when TS settled PASS (`next_workflow` is `export-skill`); FAIL, INCONCLUSIVE and pass-with-drift halt the pipeline before EX, with the verdict as the halt reason |
| QS | TS | skill name (from `repo_name`) | Forger passes the quick-skill's output name to TS |
| QS | EX | skill name | Same |
| AS | US | skill name + drift severity | The forger's gate reads the drift severity from the envelope AS printed (`drift_score`); CLEAN skips US |
| US | TS | skill name | Forger passes the `skill_name` US updated to TS: the skill `maintain` names, or the one a repair updates |
| VS | RA | architecture doc path | Already known from VS invocation |

## Circuit Breakers

Circuit breakers halt the pipeline when a workflow's output doesn't meet a quality threshold. The forger's `pipeline-gate.py` script applies the AN, TS, AS and VS rows to the result envelope a workflow printed (a field name after a slash is its spelling in the workflow's result record) and answers continue, skip or halt with a reason; CS's row is a hard halt, which stops the pipeline by itself.

| Workflow | Check | Default Threshold | Halt Condition |
|----------|-------|-------------------|----------------|
| AN | recommended units count (`unit_counts.confirmed`) | min: 1 | Fewer units than the minimum (by default, zero skillable units found) |
| CS | compilation success | must complete | Hard error during compilation |
| TS | settled verdict (`verdict` / `summary.result`, with `next_workflow`) | TS's own: `TS[min:N]` reaches TS as `--threshold=N`, else the per-pipeline defaults apply (see init.md §1b) | Any verdict but PASS, reported as the halt reason: FAIL (including a FAIL that a post-score cap forced although the score clears the threshold), INCONCLUSIVE or pass-with-drift. TS owns its score, caps and 80% floor: a score between 80% and a higher threshold that TS settles as a fallback PASS with an evidence report continues |
| AS | drift severity (`drift_score` / `summary.severity`) | not CRITICAL | CRITICAL drift found (CLEAN skips a US that comes next) |
| VS | coverage (`coverage_percentage` / `summary.coveragePercentage`) with the overall verdict (`overall_verdict` / `summary.overallVerdict`) | coverage above 0% | Zero coverage (`zero-coverage`): VS verified none of the architecture's technologies. Every verdict with coverage continues, NOT_FEASIBLE included, since RA takes each Blocked integration as a critical issue |

Override syntax: `TS[min:80]` sets the test-skill threshold to 80 for this pipeline run (the forger passes it to TS as `--threshold=80`), and `AN[min:2]` asks AN for at least two units.

### Bracket Syntax

Brackets after a workflow code (`CODE[value]`) are parsed as follows:

- **Circuit breaker override**: `min:N` where N is a number, on AN or TS (the override syntax above), e.g. `TS[min:80]`
- **Mode flag**: `auto` — e.g., `AN[auto]` activates auto mode for that workflow. The workflow's first step reads the flag from pipeline data context and routes to the appropriate auto-mode step file.
- **Target argument**: any other value — e.g., `CS[cocoindex]` passes "cocoindex" as the target to CS

The keywords `min` and `auto` match in any case (`TS[MIN:80]`). A bracket that starts like `min` but is not `min:<number>` (`TS[min:80%]`, `TS[min=80]`) is malformed: the pipeline stops before any workflow runs rather than pass it on as a target.

Only AN (a unit count) and TS (a test threshold) take `min:N`. CS, AS and VS have circuit breakers with no number to set, so a `min:N` on them, as on any other code, is ignored, and the forger warns about it. Target arguments are valid for any workflow that accepts a named input (CS, QS, BS, US, etc.).

## Pipeline State

The forger keeps a chain's state on disk, never only in the conversation, so a closed session, a killed terminal or a compacted context loses nothing. Its `scripts/pipeline-journal.py` writes the state, and nothing else does: a journal, `pipeline-journal.json`, in the run's own folder `{project-root}/_bmad-output/.skf-run/skf-forger-<run_id>/`, written when the chain starts, after every workflow, and when a resume picks the chain up again.

| Field | What it holds |
| --- | --- |
| `journal_version` | `1` |
| `run_id` | the UTC time the chain started and a random suffix (`20261001T120000Z-3f9a1c2e`), also the run folder's suffix |
| `status` | `running` from the start, `halted` once a step halted; a chain cut off mid-step stays `running` |
| `started_at`, `updated_at` | the UTC times of the journal's first and last write |
| `invocation` | the whole invocation the chain started from |
| `alias` | the pipeline alias name (`forge-auto`, `forge`, `forge-quick`, `maintain`), or null for an ad-hoc sequence |
| `args` | the first workflow's inputs, the parse's `args` (`project_path`, `pin` ...) |
| `steps` | one entry per workflow, in plan order |
| `data` | each value a workflow handed the next, by its Data Flow name (`skill_name`, `brief_path` ...); a name one call gave twice holds a list |
| `outputs` | each result or report path a workflow's envelope named, with its code |
| `history` | each halt a resume or repair picked up again: its code, reason, repair and time |

Each entry of `steps` has one shape, in the journal and in the pipeline result alike:

```json
{"code": "TS", "min": 90, "mode": null, "target": null, "flags": [], "status": "halted", "reason": "FAIL"}
```

`min`, `mode` and `target` are the plan's bracket values (Bracket Syntax), a resumed chain's first step also taking the journal's skill as its `target`, and `flags` the flags a repair adds (`--from-test-report`). `status` is `pending` (not run yet), `completed`, `skipped` (a gate passed over it) or `halted`, and `reason` is the gate's or the workflow's halt reason, a gate's reason for a skip, or null.

Every chained workflow's data context carries `pipeline_mode: true`, which marks pipeline context even for an ad-hoc sequence, and `pipeline_alias`, the journal's `alias`, which TS reads in init.md §1b for the per-pipeline threshold lookup.

## Pipeline Result

`pipeline-journal.py finish` writes each chain's result from its journal, per `output-contract-schema.md`: the per-run record `{sidecar_path}/pipeline-result-<YYYYMMDD-HHmmss>.json` (UTC; `-2`, `-3` ... when a run already took that second's name) and its copy `{sidecar_path}/pipeline-result-latest.json`, the file consumers read.

```json
{
  "skill": "skf-forger",
  "status": "partial",
  "timestamp": "2026-10-01T12:31:07Z",
  "run_id": "20261001T120000Z-3f9a1c2e",
  "outputs": [{"type": "report", "path": "forge-data/hono/1.2.0/create-skill-result-latest.json"}],
  "summary": {
    "status": "partial",
    "halt_reason": "FAIL",
    "alias": "forge-auto",
    "steps": [
      {"code": "CS", "min": null, "mode": null, "target": null, "flags": [], "status": "completed", "reason": null},
      {"code": "TS", "min": 90, "mode": null, "target": null, "flags": [], "status": "halted", "reason": "FAIL"}
    ]
  },
  "headless_decisions": [],
  "warnings": []
}
```

`status` and `summary.status` are `success` when no step halted, `partial` when a step halted after another completed, and `failed` when one halted before any completed, or when the chain stopped before its journal started (at its parse, or a `start` that failed) or lost it: such a record lists no step. `summary.halt_reason` is the halted step's `reason`, null on success, and `summary.steps` lists every step of the plan in the Pipeline State shape, one that never ran as `pending` (the example shows two of five). `headless_decisions` stays empty, and `warnings` names what `finish` could not do: save or read the journal, or delete the run folder.

## Resume and Repair

At activation the forger runs `pipeline-journal.py resume`, which reads the newest journal a stopped chain left. It offers nothing when no journal is left, when a later chain recorded a result with a step in it (any pipeline result in the sidecar, the per-run records included: a record with no step, such as a parse halt's, supersedes nothing), or when the journal's skill was tested or exported after the journal's last write: a test result record or an export manifest entry, which WS reads too, dated after it. The manifest dates an export by its day only, so an export that same day counts when the manifest was written after the journal, whichever skill that write was for. Otherwise it offers one of two things:

- **Resume** after an interruption (the journal is still `running`) or a halt that is no quality verdict, such as a workflow that hard-halted or a result the gate could not read: the chain re-runs the step it stopped on, then the rest of the plan, with the recorded alias, bracket values and arguments.
- **Repair** after a quality halt: the repair the table below gives, then the chain picks up where the table says, still with the recorded alias and threshold.

`finish` prints the same next action when the chain stops, and both print it with its `route`, the next action in one line (`US hono --from-test-report, then TS EX at the recorded threshold of 90`), and its `user_action`, what the user does before the chain picks up again (null when the chain does it all). `pipeline-journal.py reopen` applies the offer the user accepts (the Resume procedure in the forger's pipeline-mode.md), and `discard` deletes a stopped chain's run folder, so its offer is made no more.

### Repair Routes

| Halted on | Reason | `repair` | `user_action` | The chain picks up at |
| --- | --- | --- | --- | --- |
| TS | `FAIL` | `update-from-test-report` | none: `US <skill> --from-test-report` joins the plan as the next step and fixes the gaps the test report lists | TS, at the recorded threshold |
| TS | `INCONCLUSIVE` | `add-evidence` | add evidence: install skill-check, or move up a tier (the tier's tools, then `SF`) | TS |
| TS | `pass-with-drift`, `workspace-drift` | `retest-at-pinned-commit` | put the source back at the commit the skill pins | TS, without `--allow-workspace-drift` |
| AS | `CRITICAL` | `review-drift-report` | review the drift report | the step after AS |
| VS | `zero-coverage` | `create-missing-skills` | create skills for the architecture's technologies (for example `forge-quick <package>`) | VS |
| AN | `no-skillable-units`, `units-below-min`, `skipped` | `new-target` | start a new chain with another target, or with a scope hint | no resume |
| AN | `redirect` | `update-existing-skill` | run `US` on the skill the target already has | no resume |

A halt with no resume leaves no journal behind: `finish` deletes its run folder, as it does after a chain that succeeded, and its `route` is `no resume:` and the `user_action`.

## Anti-Patterns

The forger validates the pipeline sequence and warns about:

| Pattern | Issue | Suggestion |
|---------|-------|------------|
| EX before TS | Exporting untested skill | Add TS before EX |
| US without AS | Updating without audit | Run AS first to detect what changed |
| CS without BS or AN | Compiling without brief | Need a brief — use QS for quick path, or AN for brownfield |
| TS after EX | Testing after export | Move TS before EX |
| Duplicate codes | Same workflow twice | Remove duplicate |
| `min:N` on a code other than AN or TS | Threshold ignored | Remove it, or put it on TS |

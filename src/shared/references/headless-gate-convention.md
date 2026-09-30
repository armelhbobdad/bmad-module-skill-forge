# Headless Gate Convention

## Overview

Gates are user interaction points where a workflow pauses for confirmation or input. In headless mode, gates auto-resolve with their default action. This convention ensures one code path with two behaviors — interactive and headless use the same gates, the same output, and the same progression logic.

## How It Works

Every gate in a step file follows this pattern:

```
**GATE: [default action]** — Present [options] to user.
If `{headless_mode}`: auto-proceed with [default action], log: "headless: auto-[action]".
```

The gate always:
1. Prepares the same output (summary, preview, menu) regardless of mode
2. In interactive mode: displays the output and waits for user input
3. In headless mode: displays the output, logs the auto-action, records it in the run sink (see [Recording Auto-Decisions and Warnings](#recording-auto-decisions-and-warnings)), and proceeds with the default

## Resolving `{headless_mode}`

`{headless_mode}` is resolved during activation from:
1. **Args:** `--headless` or `-H` passed to the skill invocation
2. **Preferences:** `headless_mode: true` in `{sidecar_path}/preferences.yaml`
3. **Default:** `false`

Each workflow's On Activation section resolves this variable alongside other config. The forger passes it through when dispatching to workflows.

## Gate Types

### Confirm Gate (default: Continue)
The most common gate. Presents a summary and asks to continue.
- Default action: `[C] Continue`
- Headless behavior: auto-continue after displaying summary

### Review Gate (default: Approve)
Presents compiled output for review before writing.
- Default action: `[C] Continue` (approve)
- Headless behavior: auto-approve after displaying preview

### Input Gate (default: use provided args)
Requires user-supplied data (skill name, path, etc.).
- Default action: use `{headless_args}` if provided
- Headless behavior: consume pre-supplied arguments; halt if missing required input

### Choice Gate (default: first safe option)
Presents a menu with multiple options (P/I/A, etc.).
- Default action: varies per gate (documented in step file)
- Headless behavior: auto-select the default, log the choice

## Headless Args

For skills that require user input (skill name, target path, etc.), headless mode accepts arguments via the invocation. Each skill's Invocation Contract documents its required headless args.

Example: `@Ferris QS cocoindex --headless` passes `cocoindex` as the target and skips all gates.

## Recording Auto-Decisions and Warnings

Every run owns a run folder, `_bmad-output/.skf-run/<workflow>-<run_id>/` (`{run_dir}`). Its sink holds what the run decided and noticed without a person, one JSON value per line:

| File | One line per |
| --- | --- |
| `headless-decisions.jsonl` | auto-decision: a JSON object shaped like one entry of the workflow's `headless_decisions` |
| `warnings.jsonl` | warning: a JSON string, such as `"customization_resolver_unavailable: <reason>"` |

A gate appends its decision the moment it decides, and a step appends a warning when it raises it, through the shared emitter rather than by hand. For a decision, stage the object as a file in the run folder first:

```bash
uv run {emitEnvelopeHelper} record --workflow <workflow> --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "<warning>"
```

With `--workflow`, a decision the workflow's envelope schema rejects fails here, at the gate; without it, the emitter leaves the decision out when the run ends and adds a `headless_decision_invalid` warning. Because the sink is on disk, the trail survives context compaction, and a HARD HALT reports every decision taken before it.

When the On Activation customization resolver is missing or fails, the run applies only the skill's own `customize.toml`. Record `customization_resolver_unavailable: <reason>` as a warning, or pass the reason in the envelope payload as `customization_resolver_unavailable`, so a pipeline sees that the team and user overrides under `_bmad/custom/` were not applied.

## Emitting the Result Envelope

A workflow with a headless contract prints one `SKF_<NAME>_RESULT_JSON: {...}` line when a run ends and at every HARD HALT. The shared emitter builds it; the model never types it. Stage the payload as a file in the run folder, then run one command:

```bash
uv run {emitEnvelopeHelper} emit --workflow <workflow> --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
uv run {emitEnvelopeHelper} emit-halt --workflow <workflow> --run-dir "{run_dir}" < "{run_dir}/halt.json"
```

- `result-context.json` holds the envelope's fields, and optionally the `result_contract` object for the run's result files. `halt.json` holds the halt's `phase`, `reason`, `halt_reason`, `exit_code` and `path`, plus any envelope field the halt already knows, such as the skill name.
- The emitter stamps what the model must not type: the timestamp from the clock, the run id and the result file path. It folds the sink into `headless_decisions` and `warnings`, derives `exit_code` from `halt_reason`, checks the envelope against the workflow's schema, `shared/scripts/schemas/skf-<name>-result-envelope.v1.json`, and prints the line. Display that line verbatim.
- With `--result-dir` naming a folder that exists (the version folder), it also writes the run's per-run and `-latest` result files, as `output-contract-schema.md` describes. A halt before that folder exists reports through the line alone.
- Write the `emit-halt` command at each HARD HALT, naming its phase, `halt_reason` and exit code there, and resolve the helper once at activation, before the first halt can fire. The halt then emits the right line even when the step file that defines the run's success envelope was never loaded, or was compacted away.
- If the helper exits non-zero or prints no line, display the halt reason alone.

A workflow adopts the emitter by adding its schema under `src/shared/scripts/schemas/`, with the emitter's settings in its `$defs`: an entry `skf-envelope` whose `const` names the workflow, the line's prefix, the status a halt carries, the exit code of each `halt_reason` and the result file name (the emitter's docstring lists the fields). `$defs` and `const` are standard keywords, so a strict validator such as Ajv still compiles the installed schema. skf-setup calls the same helper through its `emit` and `emit-blocked` subcommands, and skf-brief-skill through `skf-emit-brief-result-envelope.py`, which stays as an alias. Like the helper it replaced, the alias refuses no payload for a key the envelope has no field for, or for a typed `exit_code`: it drops the key, derives the code, and says so in the envelope's `warnings`.

## What Headless Does NOT Skip

- Error halts (hard halts on missing files, invalid state)
- Progress output (summaries, status updates still display)
- Quality thresholds (if a step produces output below spec, it still reports the issue)

Exception: skf-setup makes its result envelope the final message of a standalone headless run, so the envelope line is all `claude -p` prints. Under `--headless` (or `--quiet`, its alias) it skips its progress output, resolves its gates without displaying them, and the health check it chains to adds nothing of its own before that envelope. Inside a forger pipeline it displays the same line and returns control to the forger. Its SKILL.md Invocation Contract states this.

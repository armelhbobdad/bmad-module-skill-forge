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
3. In headless mode: displays the output, logs the auto-action, and proceeds with the default

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

## What Headless Does NOT Skip

- Error halts (hard halts on missing files, invalid state)
- Progress output (summaries, status updates still display)
- Quality thresholds (if a step produces output below spec, it still reports the issue)

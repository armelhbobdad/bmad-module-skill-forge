---
nextStepFile: 'resolve-target.md'
---

<!-- Config: communicate in {communication_language}. -->

# Batch Mode

When `--batch <file>` is supplied, quick-skill processes a list of targets from a text file in sequence rather than a single target from arguments. Designed for unattended bulk runs (CI pipelines, mass-rebuilds, the skf-batch-skills meta-workflow when it lands).

## Input format

One target per line. Empty lines and lines starting with `#` (after optional leading whitespace) are ignored. Each non-empty line has the same shape as the single-target `target` argument, with optional space-separated per-line modifiers:

```
# A batch input file.
lodash
@vercel/og
cognee@0.5.0
https://github.com/foo/bar
https://github.com/foo/bar@2.1.0-beta

# Per-line modifiers — overrides for THIS target only:
lodash language=javascript scope=src/
cognee@0.5.0 language=python scope=cognee/api/
```

Recognised per-line modifiers:

| Modifier | Effect (this target only) |
| --- | --- |
| `language=<lang>` | Sets `language_hint` for this target — same effect as the optional `language_hint` input on a single-target run. |
| `scope=<path>` | Sets `scope_hint` for this target — same effect as the optional `scope_hint` input on a single-target run. |

Per-line modifiers shadow the global `--description` / `--exports` / `--skip-snippet` / `--no-active-pointer` overrides only when those override fields are not set. Global overrides apply to every target unless a future modifier extends per-line override syntax.

## Execution

`--batch` implies `--headless`. The batch loop runs the full quick-skill pipeline (steps 1–7) for each target in file order:

1. Set `target`, `target_version`, `language_hint`, `scope_hint` from the batch line into the workflow context.
2. Execute steps 1–7 per the normal pipeline.
3. After step 7 completes (success or HARD HALT), record the per-target outcome (target, status, exit_code, skill_package, error.code) into the batch result list.
4. If `--fail-fast` is set and the target failed, exit the batch loop immediately. Otherwise continue with the next target.

Per-target output lands in `{skill_package}/` as today, with the per-target result contract at `{skill_package}/quick-skill-result-latest.json` (success or error variant per "Result Contract on HARD HALT" above).

## Batch summary contract

After the last target completes (or `--fail-fast` triggers an early exit), write the batch summary at:

```
{skills_output_folder}/_batch/quick-skill-batch-{YYYYMMDD-HHmmss}.json
{skills_output_folder}/_batch/quick-skill-batch-latest.json   (copy, not symlink)
```

Schema:

```json
{
  "skill": "skf-quick-skill",
  "mode": "batch",
  "status": "success | partial | failed",
  "timestamp": "<ISO 8601 UTC>",
  "input_file": "<path passed to --batch>",
  "targets_total": 0,
  "succeeded": 0,
  "failed": 0,
  "fail_fast_triggered": false,
  "results": [
    {
      "target": "<line from batch file>",
      "status": "success | error",
      "exit_code": 0,
      "skill_package": "<absolute path or null>",
      "error_code": null
    }
  ]
}
```

`status` resolves as: `"success"` when `failed == 0`; `"partial"` when `failed > 0 && succeeded > 0`; `"failed"` when `succeeded == 0`. `fail_fast_triggered` is `true` only when `--fail-fast` aborted the loop early — `targets_total` then reflects the count actually attempted, not the file's line count.

## Headless events

Batch mode emits per-target boundary events on stderr in addition to the per-step events documented in Workflow Rules:

```
{"batch":<n>,"target":"<target>","status":"start"}
{"batch":<n>,"target":"<target>","status":"done","exit":<code>}
{"batch":<n>,"target":"<target>","status":"fail","exit":<code>,"error_code":"<class>"}
```

`<n>` is the 1-based index of the target in the parsed list. After the loop ends, emit one final batch-summary event:

```
{"batch_summary":true,"targets_total":N,"succeeded":K,"failed":M,"status":"<...>","fail_fast_triggered":<bool>}
```

## Exit code

The batch process exits with code `0` when `failed == 0`, otherwise with the exit code of the first failed target (so automators that already branch on the single-target exit-code map continue to work without batch-specific handling). When `--fail-fast` triggers, the exit code is the failing target's code.

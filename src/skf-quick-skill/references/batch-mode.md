---
nextStepFile: 'resolve-target.md'
healthCheckStepFile: 'health-check.md'
quickBatchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-quick-batch.py'
  - '{project-root}/src/shared/scripts/skf-quick-batch.py'
---

<!-- Config: communicate in {communication_language}. -->

# Batch Mode

When `--batch <file>` is supplied, quick-skill processes a list of targets from a text file in sequence rather than a single target from arguments. Designed for unattended bulk runs: CI pipelines, mass-rebuilds, and batch meta-workflows. The batch's place in the file and every target's outcome live in the batch run folder, kept by `skf-quick-batch.py`, never only in context, so a context compaction mid-batch loses neither, and the helper computes the counts, the status and the exit code.

## Before the Batch Starts

SKILL.md On Activation step 5 loads this file before anything else. `--skip-snippet` and `--no-active-pointer` apply to every target. `--description` and `--exports` are single-target overrides: one description or export list cannot fit every target. `--language-hint` and `--scope-hint` are single-target flags too: a batch line gives its own target a hint with `language=` and `scope=` (Input format below). When any of the four was passed, HARD HALT with **exit code 2 (input-invalid)** before any target runs: "**`{the flags passed}` do not combine with `--batch`.** They would apply the same description, export list or hint to every skill in the batch. Run each target that needs its own description or export list on its own, give a batch line its own `language=` or `scope=`, or drop the flag and let each target's extraction supply it." Stage `{"phase": "on-activation", "halt_reason": "input-invalid", "reason": "<the message's first sentence>", "skill_package": null, "details": {"flags": [<the flags passed>], "batch_file": "<file>"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`; no batch summary is written.

Otherwise `--batch` implies `--headless`: set `{headless_mode}` to true (log "headless: coerced by --batch" if it was false) and go on to Execution.

## Input format

One target per line. Empty lines and lines starting with `#` (after optional leading whitespace) are ignored. Each non-empty line has the same shape as the single-target `target` argument, with optional space-separated per-line modifiers:

```
# A batch input file.
lodash
@vercel/og
cognee@0.5.0
https://github.com/foo/bar
https://github.com/foo/bar@2.1.0-beta

# Per-line modifiers: overrides for THIS target only
lodash language=javascript scope=src/
cognee@0.5.0 language=python scope=cognee/api/
```

Recognised per-line modifiers:

| Modifier | Effect (this target only) |
| --- | --- |
| `language=<lang>` | Sets `language_hint` for this target: the same effect as `--language-hint` on a single-target run. |
| `scope=<path>` | Sets `scope_hint` for this target: the same effect as `--scope-hint` on a single-target run. |

The target stays whole, its version included (`cognee@0.5.0`, `requests==2.31.0`): step 1 §1b reads the version as it reads a single target's. A modifier key may be in any letter case; its value must not be empty, and each modifier may appear once. A line with any other word after its target is taken whole as the target, so step 1 cannot parse it and that target fails while the rest of the batch runs.

## Execution

`{batch_dir}` is the run folder SKILL.md On Activation step 1 created (`{run_dir}` until the first target), and `{batch_file}` the file given to `--batch`. After a compaction, `{batch_dir}` is the parent folder of the target's `{run_dir}`: the `{project-root}/_bmad-output/.skf-run/skf-quick-skill-*` folder that holds `batch.jsonl`. Bind `{quickBatchHelper}` ← `helpers.quickBatch` in `{batch_dir}/helpers.json`, which SKILL.md On Activation step 1 wrote; take the first existing path in `{quickBatchProbeOrder}` only when that file holds no `quickBatch`.

### 1. Start the Batch

```bash
uv run {quickBatchHelper} start "{batch_file}" --run-dir "{batch_dir}" [--fail-fast]
```

Pass `--fail-fast` when it was given. The helper parses the file and writes the batch file `{batch_dir}/batch.jsonl`, status running and every target pending; run again on the same file, after a compaction for example, it changes nothing. If it exits non-zero, the `halt_reason` of its stderr JSON names the halt; no target runs and no batch summary is written (`references/halt-contract.md`):

- **`input-invalid`** (a batch file it cannot read, or a run folder that holds another batch), or no path in `{quickBatchProbeOrder}` exists (an incomplete install): HARD HALT with **exit code 2 (input-invalid)**: display "**The batch cannot start:** {its `message`, or: skf-quick-batch.py is missing, re-install SKF}", stage `{"phase": "batch-mode", "halt_reason": "input-invalid", "reason": "The batch cannot start: <that message>", "skill_package": null, "details": {"batch_file": "{batch_file}"}}` as `{batch_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{batch_dir}" --target stderr < "{batch_dir}/halt.json"`.
- **`write-failure`** (the batch run folder cannot be written, so it cannot hold `halt.json` either): HARD HALT with **exit code 4 (write-failure)**: display "**The batch cannot start:** {its `message`}" and emit with nothing to stage in:

  ```bash
  uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'
  {"phase": "batch-mode", "halt_reason": "write-failure", "reason": "The batch cannot start: <its message, one line>", "skill_package": null}
  SKF_JSON
  ```

### 2. Take the Next Target

```bash
uv run {quickBatchHelper} next --run-dir "{batch_dir}"
```

- **`"status": "next"`**: the helper printed the target's `start` event on stderr: display it verbatim, then print step 1's `start` event (`references/halt-contract.md`, Headless Events). Bind `{run_dir}` ← its `run_dir` (the target's own run folder, created empty), and set `target`, `language_hint` and `scope_hint` from it. When `{batch_dir}/resolver-warning.txt` exists (SKILL.md On Activation step 3 wrote it, so the customization resolver could not run), record it in the target's sink: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{batch_dir}/resolver-warning.txt")"`. Nothing else carries over from the previous target: its version, repository, extraction, compiled output, `{skill_package}` and summary values all start empty. Then load, read in full and execute `{nextStepFile}`: steps 1 to 6 run for this target.
- **`"status": "record"`**: target `batch` ended, its payload staged, before §3 recorded it (a compaction came between its envelope and §3): go to §3 with that `batch`, never running it again.
- **`"status": "done"`**: no target is pending, or `--fail-fast` ended the batch after a failed target. Go to §4.

If it exits non-zero (the target's run folder cannot be created, or the batch file is gone or unreadable), the batch cannot go on: display "**The batch stopped:** {its `message`}" and HARD HALT with **exit code 4 (write-failure)**: no other target runs and the health check does not run. Emit with nothing to stage in, as §1 does:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'
{"phase": "batch-mode", "halt_reason": "write-failure", "reason": "The batch stopped: <its message, one line>", "skill_package": null}
SKF_JSON
```

### 3. Record the Target

Every target ends here: step 6 §4 returns here when the target finishes, and every HARD HALT of steps 1 to 6 returns here after its envelope (`references/halt-contract.md`, In `--batch`), the step 5 ownership halt included. Control returns here even when the step that ended the target reads as the end of the run. Record it:

```bash
uv run {quickBatchHelper} record --run-dir "{batch_dir}" --batch {batch} --target stderr
```

`{batch}` is the number §2's `next` printed. The helper reads how the target ended from what its run folder staged for the emitter (`halt.json`, or step 6's `result-context.json`), appends the outcome to the batch file, removes the run folder of a target that succeeded, and prints the target's `done` or `fail` event on stderr: display it verbatim. Then go back to §2. If it exits non-zero, its `message` names what is missing: stage the payload the target ended with and record again, once. If it exits non-zero a second time (the batch file cannot be written, or the staged `halt.json` is not JSON or names a `halt_reason` that maps to no exit code), the outcome cannot be kept and the batch cannot go on: display "**The batch stopped:** {its `message`}" and HARD HALT with **exit code 4 (write-failure)**. This halt ends the batch, not only the target: do not go back to §2, which would hand the same target back, no other target runs and the health check does not run. Emit with nothing to stage in, as §1 does:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'
{"phase": "batch-mode", "halt_reason": "write-failure", "reason": "The batch stopped: <its message, one line>", "skill_package": null}
SKF_JSON
```

### 4. Batch Summary

```bash
uv run {quickBatchHelper} summarize --run-dir "{batch_dir}" --output-dir "{batchOutputPath}" --target stderr
```

The helper counts the targets, sets the batch status and exit code, writes the batch summary and its `-latest` copy in `{batchOutputPath}`, appends the final status to the batch file (and removes the batch run folder when no target failed), and prints the `batch_summary` event on stderr: display it verbatim. Then bind `{result_envelope_line}` empty, so the health check shows no line an earlier workflow of the session bound, print step 7's `start` event, and load, read in full and execute `{healthCheckStepFile}`: the health check runs once per batch, here. The batch ends with the event's `exit_code`.

If `summarize` exits non-zero (a target is still pending, or the batch file is gone or unreadable), it wrote no summary file: display "**The batch stopped:** {its `message`}" and HARD HALT with **exit code 4 (write-failure)**: the health check does not run. When an earlier `summarize` already printed the `batch_summary` event (a compaction came before the health check), that event stays the batch's result. Emit with nothing to stage in, as §1 does:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'
{"phase": "batch-mode", "halt_reason": "write-failure", "reason": "The batch stopped: <its message, one line>", "skill_package": null}
SKF_JSON
```

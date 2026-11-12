---
nextStepFile: 'load-brief.md'
healthCheckStepFile: 'health-check.md'
# Resolve `{quickBatchHelper}` to the first existing path. It keeps the
# batch on disk: §1 starts it, §2 hands out each brief, §3 records how each
# one ended and §4 ends the batch. If neither path exists, §1 halts before
# any brief compiles.
quickBatchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-quick-batch.py'
  - '{project-root}/src/shared/scripts/skf-quick-batch.py'
# HARD HALT helper (Execution).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Batch Mode

With `--batch`, create-skill compiles every brief the paths after the flag name, one after another: each path is a `skill-brief.yaml`, or a folder whose `skill-brief.yaml` files (at any depth, hidden folders left out) are compiled; with no path, the briefs under `{forge_data_folder}`. `skf-quick-batch.py` keeps the batch in its run folder, never only in context: it checks every brief with the brief schema validator before the first one compiles, hands out each brief in turn, records how each one ended, and computes the counts, the status and the exit code. A HARD HALT ends its brief, not the batch.

## Execution

Resolve `{quickBatchHelper}` ← the first existing path in `{quickBatchProbeOrder}`, and `{emitEnvelopeHelper}`, which every HARD HALT here emits through, ← the first existing path in `{emitEnvelopeProbeOrder}` when it is not bound. The helper names the batch run folder, `{batch_dir}`, after the briefs: the same briefs always get the same folder, so a batch a session ended mid-way is found again (run `--batch` with the same briefs and it goes on with the brief it was working on, which compiles again from the start), and a batch of other briefs, from another terminal, never touches it. After a compaction, `{batch_dir}` is the parent folder of the brief's `{run_dir}`, and §1's `start` run again with the same briefs prints it without changing the batch.

### 1. Start the Batch

```bash
uv run {quickBatchHelper} start --briefs {batch_paths} --run-root "{project-root}/_bmad-output/.skf-run"
```

`{batch_paths}` is each path given to `--batch`, quoted, or `"{forge_data_folder}"` when none was given. The helper finds the briefs and checks each one, and records each brief the validator refuses as failed, with its `halt_reason` (`brief-missing`, `brief-malformed` or `brief-invalid`) and the validator's first message, before any brief compiles; a brief whose `name` an earlier brief already has is refused the same way (`brief-invalid`), since both would compile into one skill folder. Bind `{batch_dir}` ← its `batch_dir`. When On Activation step 3 kept a `{customization_resolver_unavailable}` reason, write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{batch_dir}/resolver-warning.txt` with a file write, never `echo`: load-brief.md §0 records it in each brief's sink, after a compaction too. Display the plan: "**Batch:** {targets_total} briefs, {targets_total minus the `rejected` count} to compile." and, for each `rejected` entry, "Not compiled: `{target}`: {message}". When `resumed` is true, add "Resuming the batch: {recorded} briefs already ended."

If it exits non-zero, no brief compiles: the `halt_reason` of its stderr JSON names the halt. Display "**The batch cannot start:** {its `message`, or: skf-quick-batch.py is missing, re-install SKF}", and stop:

- `brief-missing`, no brief under the paths: **HARD HALT** (exit code 2, `brief-missing`, phase `batch-mode`; emit with nothing to stage in, below).
- `helper-missing`, the validator cannot load, or no path in `{quickBatchProbeOrder}` exists: **HARD HALT** (exit code 3, `helper-missing`, phase `batch-mode`; emit with nothing to stage in, below).
- `write-failed`, the batch folder cannot be written, or holds an unfinished batch of other briefs, which start never deletes: **HARD HALT** (exit code 4, `write-failed`, phase `batch-mode`; emit with nothing to stage in, below).

No run folder holds a payload yet, so the halt's envelope comes from the command alone. Every halt of this file emits this way, with the reason it gives:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --target stderr <<'SKF_JSON'
{"phase": "batch-mode", "halt_reason": "<the halt_reason>", "reason": "The batch cannot start: <that message, one line>", "summary": {"halt_reason": "<the halt_reason>", "evidence_report": null}}
SKF_JSON
```

### 2. Take the Next Brief

```bash
uv run {quickBatchHelper} next --run-dir "{batch_dir}"
```

- **`"status": "next"`**: display the `start` event the helper printed on stderr. Bind `{run_dir}` ← its `run_dir`, the brief's own run folder, created empty, and `{brief_path}` ← its `target`. Nothing else carries over from the previous brief: its source, tree, extraction, staged skill and summary values all start empty. Then load, read in full and execute `{nextStepFile}`: steps 1 to 8 run for this brief.
- **`"status": "record"`**: brief `batch` ended, its payload staged, before §3 recorded it (a compaction came between its envelope and §3): go to §3 with that `batch`, never compiling it again.
- **`"status": "done"`**: no brief is pending. Go to §4.

If it exits non-zero (the brief's run folder cannot be created, or the batch file is gone or unreadable), the batch cannot go on: display "**The batch stopped:** {its `message`}" and **HARD HALT** (exit code 4, `write-failed`, phase `batch-mode`; emit with nothing to stage in, as §1 does, with the reason "The batch stopped: <its message>").

### 3. Record the Brief

Every brief ends here: step 8 §6 sends a finished brief here, and every HARD HALT of steps 1 to 7 returns here after its envelope (each stage's Rules say so). Control returns here even when the step that ended the brief reads as the end of the run. Record it:

```bash
uv run {quickBatchHelper} record --run-dir "{batch_dir}" --batch {batch} --target stderr
```

`{batch}` is the number §2's `next` printed. The helper reads how the brief ended from what its run folder staged for the emitter (`halt.json`, or step 8's `result-context.json`), appends the outcome to the batch file, removes the run folder of a brief that finished (a halted brief keeps its folder for a look), and prints the brief's `done` or `fail` event on stderr: display it verbatim. Then go back to §2. If it exits non-zero, its `message` names what is missing: stage the payload the brief ended with and record again, once. If it exits non-zero a second time (the batch file cannot be written, or a `halt_reason` maps to no exit code), the outcome cannot be kept: display "**The batch stopped:** {its `message`}" and **HARD HALT** (exit code 4, `write-failed`, phase `batch-mode`; emit with nothing to stage in, as §1 does, with the reason "The batch stopped: <its message>").

### 4. Batch Summary

```bash
uv run {quickBatchHelper} summarize --run-dir "{batch_dir}" --output-dir "{skills_output_folder}/_batch" --target stderr
```

The helper counts the briefs, sets the batch status and exit code, writes the summary to `{skills_output_folder}/_batch/create-skill-batch-{YYYYMMDD-HHmmss}.json` and its `create-skill-batch-latest.json` copy (`skill`, `mode`, `status`, `timestamp`, `input_briefs`, `targets_total`, `succeeded`, `failed`, `fail_fast_triggered`, `exit_code`, and `results[]`, one per brief with its `batch`, `target`, `status`, `exit_code`, `skill_package` and `error_code`), removes the batch run folder when no brief failed, and prints the `batch_summary` event on stderr: display it verbatim, then "Batch complete: {succeeded} of {targets_total} briefs compiled." and, when `failed` is above 0, the `target` and `error_code` of each failed `results[]` entry of the summary file.

Then bind `{result_envelope_line}` empty, so the health check shows no line an earlier workflow of the session bound, and load, read in full and execute `{healthCheckStepFile}`: the health check runs once per batch, here. The batch ends with the event's `exit_code`: 0 when every brief finished, else the highest exit code among the briefs that failed.

**Reading a batch.** Under `--batch`, a caller reads the batch's `batch_summary` event and the summary file its `summary_path` names, never `create-skill-batch-latest.json` in its place: that copy holds the last batch summary written, which may be another batch's. The event comes before the health check, so a caller reads it from the session's output stream (`claude -p --output-format stream-json`) or transcript, not from the final message. A printed `batch_summary` event stays the batch's result even if a halt line follows it. A batch that printed no `batch_summary` event has no batch result, whatever the process exit code: a halt line of its own (phase `batch-mode`) says why it stopped, and with no halt line it was cut off or could not print its halt line. A target it printed a `done` or `fail` event for ended as that event says, and a brief the plan listed as not compiled ended failed with its message; a target with a `start` event and no end event has no result, and any other target with no event did not run in this session. When the event's `summary_path` is null, the per-batch file was not written (its `summary_write_failed` warning says why): the event and `{batch_dir}/batch.jsonl`, which the helper then keeps, are the batch's result, never `create-skill-batch-latest.json`. A `summary_write_failed` warning beside a set `summary_path` means only the `-latest` copy failed: the file it names is still the batch's result. After a cut-off batch, run `--batch` again with the same briefs: while the batch has no summary, it finds the batch folder again and goes on with the brief it was working on (Execution, above). If `summarize` already ran but its event never reached the caller, `start` begins a new batch from the first brief, and that batch's summary is the per-batch file in `{skills_output_folder}/_batch/` whose `input_briefs` match.

If `summarize` exits non-zero (a brief is still pending, or the batch file is gone or unreadable), the health check does not run: display "**The batch stopped:** {its `message`}" and **HARD HALT** (exit code 4, `write-failed`, phase `batch-mode`; emit with nothing to stage in, as §1 does, with the reason "The batch stopped: <its message>"). The summary files may be missing then, but each brief's own result contract is in its `{forge_version}`, and `create-skill-batch-latest.json` may be another batch's, so it is never read in its place.

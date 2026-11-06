# Output Contract Schema

Every pipeline-capable skill writes a result JSON file at its final step. This enables reliable CI integration and pipeline chaining.

## Schema

```json
{
  "skill": "skf-skill-name",
  "status": "success" | "failed" | "partial",
  "timestamp": "ISO-8601",
  "run_id": "<run id>",
  "outputs": [
    {"type": "report|skill|manifest|config", "path": "relative/path/to/file"}
  ],
  "summary": {
    // skill-specific summary fields
  },
  "headless_decisions": [ /* the run's auto-decisions */ ],
  "warnings": [ /* the run's non-fatal warnings */ ]
}
```

The shared emitter stamps `timestamp` (UTC, from the clock), `run_id` (when the run has a run folder), `headless_decisions` and `warnings` (from the run sink, see `headless-gate-convention.md`) into the record it writes. The workflow supplies the rest.

## Filenames

Each run writes **two files** to `{output_dir}`:

1. **Per-run record** (audit trail): `{skill-name}-result-{YYYYMMDD-HHmmss}.json`
   - Timestamp is UTC, resolution to seconds, for example `update-skill-result-20260413-145230.json`
   - When a run of the same workflow already took that second's name, the emitter appends `-2`, `-3` and so on (`update-skill-result-20260413-145230-2.json`), so two runs that end in the same second never share a file
   - Never overwritten by subsequent runs, so it keeps a durable audit trail across retries, aborts, and re-runs
2. **Stable latest pointer** (a stable path, not a run's result): `{skill-name}-result-latest.json`
   - A **copy** (not a symlink) of the per-run record just written
   - At a deterministic path, so a reader finds `summary.*` without enumerating timestamps: it holds the last run whose emitter wrote this copy
   - Overwritten on every successful write

Write the per-run record first, then copy it to the `-latest.json` path. If the copy fails, the per-run record still exists — the run is not lost.

**Consumers (forger, CI, chained workflows):** a caller that started a run reads that run's own `SKF_<NAME>_RESULT_JSON` envelope line. A run that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result, and `{skill-name}-result-latest.json` may then describe an earlier run, so it is never read in its place. A tool that looks up the last run of a skill rather than one it started (skf-find-test-report.py, forge-status.py) may read the copy. Do not enumerate timestamped files unless inspecting prior-run history. Under `--batch` (skf-quick-skill, skf-create-skill), a batch's result is its `batch_summary` event and the summary file its `summary_path` names, never the `quick-skill-batch-latest.json` or `create-skill-batch-latest.json` copy: that copy holds the last batch summary written, which may be another batch's, and a batch that printed no `batch_summary` event has no batch result (each workflow's `references/batch-mode.md`).

## Writing the Files

The shared emitter, `shared/scripts/skf-emit-result-envelope.py`, writes both files when it builds the run's `SKF_<NAME>_RESULT_JSON` envelope (see `headless-gate-convention.md`). Pass the version folder as `--result-dir`:

```bash
uv run {emitEnvelopeHelper} emit --workflow <workflow> --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

- The file name's stem comes from the workflow's envelope schema (`result_file` in the emitter settings its `$defs` holds under `skf-envelope`), and the emitter chooses the per-run name, suffix included. A workflow whose settings name no result file writes none, and ignores `--result-dir` with a `result_dir_ignored` warning.
- The record is the payload's `result_contract` object with the stamped fields above, and with the payload's own `status` and `summary` when the contract leaves them out, so a workflow lists its summary once. A payload without one records the envelope itself, the error variant several workflows write on a HARD HALT (`emit-halt` takes `--result-dir` too).
- Each file is written atomically, the per-run record first and then its `-latest.json` copy. A write that fails adds a `result_file_write_failed` warning to the envelope, and a failed per-run record also leaves its `result_path` null; the envelope line still prints.
- When `--result-dir` names no folder that exists, nothing is written: a halt before the version folder exists reports through the envelope line alone.

Workflows that have not adopted the emitter yet still assemble the record in their terminal step. skf-create-skill writes each brief's record through the emitter from step 8 (`references/report.md`), and a halt's from step 7 on. skf-quick-skill writes both through the emitter: the success-variant contract from `finalize.md` §3's `result_contract`, and the error variant, its envelope, at a HARD HALT once the version folder holds `metadata.json` (`references/halt-contract.md`).

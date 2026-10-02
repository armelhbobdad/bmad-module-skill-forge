<!-- Config: a machine-parsed contract. The shared emitter builds every line; never type one. -->

# Headless Result Envelope

The single-line `SKF_EXPORT_RESULT_JSON: {…}` envelope export-skill emits on non-interactive (`{headless_mode}`) runs. Pipeline consumers parse it to branch on the run's outcome; `shared/scripts/schemas/skf-export-result-envelope.v1.json` describes each field. The shared emitter builds every line from the payload the run passes it on stdin, checks it against that schema and prints it.

`{emitEnvelopeHelper}` is the emitter SKILL.md's On Activation resolved: the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. `{run_dir}` is the run folder a headless run created under `{project-root}/_bmad-output/.skf-run/`: its sink holds the auto-decision each gate recorded, which the emitter folds into every line as `headless_decisions`.

## Emission rule

- **Success / dry-run:** step 6 (`summary.md` §6) runs `emit` once, on **stdout**, before chaining to step 7.
- **Every HARD HALT** of a headless run: run `emit-halt` as below, which prints the line on **stderr** with `status: "error"`, then exit with the halt's code (Exit Codes below). An interactive halt displays its message only.

## Emitting a Halt

Each HARD HALT a headless run can reach names its exit code, its `halt_reason` and its phase in the step files; every other field follows the run's state as below. Pass the halt's payload in a quoted heredoc, so no value is expanded. Each value is a JSON string: write a path with `/` in place of `\`, and a quote inside the message as a backtick.

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-export-skill [--run-dir "{run_dir}"] --target stderr <<'SKF_JSON'
{"phase":"<phase>","reason":"<the halt message>","halt_reason":"<halt_reason>","skills":["<name>"]}
SKF_JSON
```

- `phase` is the phase the halt site names, `<step file> §<section>` (for example `update-context §9`), and `reason` is the message the halt displays, on one line.
- `halt_reason` is the value the halt site names. The emitter derives `exit_code` from it and sets `status: "error"`; leave both out.
- Always pass `skills`, the resolved batch (`[]` only before step 1 bound `skill_batch`, as at every On Activation halt).
- Add `context_files_updated`, the context files step 4 §9 wrote before the halt, once it has written one, and `manifest_path`, the `{manifest_path}` step 4 §9b bound, once the manifest is written. Before that, leave each out: the emitter gives `context_files_updated` `[]` and `manifest_path` `null`.
- Pass `--run-dir` once On Activation bound `{run_dir}`, so the line carries the decisions taken before the halt. A halt writes no result file.

Display the line the emitter prints. If it exits non-zero or prints no line, display the halt reason alone.

## Exit Codes

Every HARD HALT exits with a stable code, so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by (halt site → `halt_reason`)                                                         |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal); also `status="dry-run"` when `--dry-run` is set                          |
| 2    | input-missing        | step 1 §1: a headless run with no `skill_name` and no `--all` (a non-interactive run cannot answer the skill-selection menu) → `input-missing` |
| 3    | resolution-failure   | step 1 §1 (discovery finds no skills on disk / in the manifest; the export manifest does not parse; context-file resolution refuses an unknown `--context-file` value or cannot read the IDE mapping); step 1 §2 (the inventory helper finds no version of a named skill to export, or its required artifacts are missing or its metadata is invalid: export-gate FAIL); multi-skill batch (any skill failing §2 validation halts the whole batch) → `resolution-failure`; step 1 §2 flat fallback (a flat `SKILL.md` with no SKF marker in its `metadata.json`, so SKF will not migrate or export it) → `not-skf-output` |
| 4    | write-failure        | On-Activation §4 (the run folder cannot be created) or §5 pre-flight write check, or step 4 §9c (a snippet write fails) → `write-failed`; On-Activation §4 (a required helper is missing), step 3 §4 (the token counter fails), step 4 §3b (an orphaned file's clear fails), §4b (the body cannot be built, for example a context file that is not UTF-8 text) or §9 (a write fails its check) → `context-rebuild-failed`; step 4 §9b manifest write → `manifest-write-failed` |
| 5    | state-conflict       | step 4 §4b or §5: `check` finds a `<!-- SKF:BEGIN` marker that no `<!-- SKF:END -->` closes in a target context file → `malformed-markers` |
| 6    | user-cancelled       | step 1 §6 gate `[X]`/cancel; step 1 §1b snippet root: the layout question [S]/[X] or the mismatch gate (a)/(c); step 4 §8 gate `[X]`/cancel; step 4 §4c.1 orphan-row (c) Cancel; any prompt accepting `cancel`/`exit`/`:q` → `user-cancelled` |

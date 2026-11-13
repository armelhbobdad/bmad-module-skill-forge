<!-- Config: a machine-parsed contract. The shared emitter builds every line; never type one. -->

# Headless Result Envelope

The single-line `SKF_EXPORT_RESULT_JSON: {…}` envelope export-skill emits on non-interactive (`{headless_mode}`) runs. Pipeline consumers parse it to branch on the run's outcome; `shared/scripts/schemas/skf-export-result-envelope.v1.json` describes each field. The shared emitter builds every line from the payload the run passes it on stdin, checks it against that schema and prints it.

`{emitEnvelopeHelper}` is the emitter SKILL.md's On Activation resolved: the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. `{run_dir}` is the run folder a headless run created under `{project-root}/_bmad-output/.skf-run/`: its sink holds the auto-decision each gate recorded, which the emitter folds into every line as `headless_decisions`.

## Run Folder

When `{headless_mode}` is true, SKILL.md's On Activation §4 creates the run folder, whose sink holds the headless auto-decisions and warnings:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-export-skill-XXXXXXXX"
```

Bind `{run_dir}` ← the path it prints. Step 5 deletes it once the run's envelope is built; a HARD HALT leaves it in place. If it cannot be created, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation §4`. When `{customization_resolver_unavailable}` is set, record it there: write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a file write (a resolver error can hold quotes or `$( )`, so never echo it or type it into an argument), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`.

The Run log rule of SKILL.md's Workflow Rules records each warning a step displays as `<code>: <skill>: <detail>`: `<skill>` is the skill the warning names, `-` when it names none, and `<detail>` is the displayed text on one line, with each `'` written as a backtick. A warning about the skill a step is processing, such as "This skill failed its last test" or a gotchas warning, names that skill, and a `'` in `<skill>` is written as a backtick too. The emitter folds them into every line as `warnings`. Each code, where its warning is displayed:

- `unknown_ide`: load-skill §1, each `resolve-targets` warning
- `test_report_fail`, `test_report_pass_with_drift`, `test_report_inconclusive`, `test_report_no_verdict`, `test_report_not_found`, `test_report_unchecked` and `test_report_warning`: load-skill §4b
- `export_gate_warnings`: load-skill §5
- `gotchas_left_off`, `gotchas_carried` and `gotchas_dropped_stale`: generate-snippet §3a
- `snippet_trimmed`: generate-snippet §4
- `orphan_context_malformed`: update-context §3b
- `managed_section_skipped_integrity`, `managed_section_skipped_deprecated`, `managed_section_skipped_missing_snippet`, `managed_section_skipped_malformed_snippet` and `managed_section_warning`: update-context §4c

## Emission rule

- **Success / dry-run:** step 5 (`summary.md` §6) runs `emit` once, on **stdout**, before chaining to step 6.
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
- Add `context_files_updated`, the context files step 3 §9 wrote before the halt, once it has written one, and `manifest_path`, the `{manifest_path}` step 3 §9b bound, once the manifest is written. Before that, leave each out: the emitter gives `context_files_updated` `[]` and `manifest_path` `null`.
- Pass `--run-dir` once On Activation bound `{run_dir}`, so the line carries the decisions taken before the halt. A halt writes no result file.

Display the line the emitter prints. If it exits non-zero or prints no line, display the halt reason alone.

## Exit Codes

Every HARD HALT exits with a stable code, so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by (halt site → `halt_reason`)                                                         |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 6 (terminal); also `status="dry-run"` when `--dry-run` is set                          |
| 2    | input-missing        | step 1 §1: a headless run with no `skill_name` and no `--all` (a non-interactive run cannot answer the skill-selection menu) → `input-missing` |
| 3    | resolution-failure   | step 1 §1 (discovery finds no skills on disk / in the manifest, or its `exportable` call cannot read the export manifest or finds `{skills_output_folder}` is not a folder; the export manifest does not parse, also when step 1 §1b's probe reads it; context-file resolution refuses an unknown `--context-file` value or cannot read the IDE mapping; `--version` comes with `--all` or with several skills); step 1 §2 (the inventory helper finds no version of a named skill to export, or the `--version` version has no package on disk, is not a version folder of the skill (such as `active`) or the export manifest marks it deprecated, or its `migrate` refuses to move a flat SKF skill into the versioned layout, or its required artifacts are missing or its metadata is invalid: export-gate FAIL); multi-skill batch (any skill failing §2 validation halts the whole batch) → `resolution-failure`; step 1 §2 flat fallback (a flat `SKILL.md` with no SKF marker in its `metadata.json`, so SKF will not migrate or export it) → `not-skf-output` |
| 4    | write-failure        | On-Activation §4 (the run folder cannot be created) or §5 pre-flight write check, step 3 §9b (with `--version`, the `active` link cannot be moved, before any manifest write), or step 3 §9c (a snippet write fails) → `write-failed`; On-Activation §4 (a required helper is missing), step 1 §1 (with `--version`, `skf-atomic-write.py` is missing), step 2 §2.5 (the prior snippet or the export manifest cannot be read), §3a (the gotchas cannot be placed, after one corrected retry) or §4 (the token counter fails, or the snippet draft fails its check after one corrected retry), step 3 §4b (the body cannot be built, for example a context file that is not UTF-8 text), §4c (`assemble` refuses the snippet draft of a skill of the batch), §6 (the change preview cannot be built) or §9 (a write fails its check, or an orphaned file's clear fails) → `context-rebuild-failed`; step 3 §9b manifest write → `manifest-write-failed` |
| 5    | state-conflict       | step 3 §4b or §5: `check` finds a `<!-- SKF:BEGIN` marker that no `<!-- SKF:END -->` closes in a target context file → `malformed-markers` |
| 6    | user-cancelled       | step 1 §6 gate `[X]`/cancel; step 1 §1b snippet root: the layout question [S]/[X] or the mismatch gate (a)/(c); step 3 §8 gate `[X]`/cancel; step 3 §4c.1 orphan-row (c) Cancel; any prompt accepting `cancel`/`exit`/`:q` → `user-cancelled` |

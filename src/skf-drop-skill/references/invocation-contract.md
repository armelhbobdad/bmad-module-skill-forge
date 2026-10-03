# Invocation Contract: skf-drop-skill

The arguments, gates, exit codes and headless result envelope of `skf-drop-skill`. Interactive runs do not need this file; headless automators and pipelines read it, and the SKILL.md On-Activation HALTs follow its Halt Envelope section.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required], mode (deprecate/purge) [required], version (`all` or one version) [required for a skill in the manifest; a draft takes only `all`]. An argument supplied at invocation answers its step 1 prompt in either mode, so that prompt is not shown |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--dry-run` (run selection and display the §10 confirmation block, then exit with `status="dry-run"`: no manifest mutation, no file deletion) |
| **Gates** | step 1: Input Gate [use args] (§4 skill), Scope Gate [use args] (§6 version), Mode Gate [use args] (§8 mode), Confirm Gate [Y] |
| **Outputs** | Updated manifest, rebuilt context files, (purge: deleted directories), `drop-skill-result-{YYYYMMDD-HHmmss}.json` (UTC) and `drop-skill-result-latest.json` in `{skills_output_folder}` (none for a dry run or a HALT); a run folder under `{project-root}/_bmad-output/.skf-run/`, kept only after a HALT, except an interactive HALT in step 1 or 2, which deletes it |
| **Headless** | Gates auto-resolve with their default action (SKILL.md Workflow Rules); select.md §6 and §8 halt when the `version` or `mode` argument a headless run must pass is missing. Any non-empty `forbid_purge_in_headless`, set under `[workflow]` in a team or personal override (never in the bundled `customize.toml`, which every update overwrites), stops a headless `mode=purge` at On-Activation §4 (exit code 6, `halt_reason: "headless-purge-forbidden"`) when the customization resolver runs. When it cannot, including an override file that fails to parse, the run warns `customization_resolver_unavailable` and the bundled empty value leaves the guard off. A key written without the `[workflow]` line is ignored with no warning, and the guard stays off. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every hard HALT exits with a stable code; the step files name the exact `halt_reason` and phase at each HALT site, and the envelope below carries both.

| Code | Meaning              | Raised by (class) |
| ---- | -------------------- | ----------------- |
| 0    | success              | step 4 (terminal) |
| 2    | input-missing / input-invalid | step 1 input gates: a missing or unmatched `skill_name`, `version` or `--mode` value (§4 / §6 / §8), or a draft skill given a specific `version` or `mode=deprecate` |
| 3    | resolution-failure   | step 1 §2 corrupt manifest, §3 nothing to drop |
| 4    | write-failure        | On-Activation §4, or step 1 §2 when the roster helper cannot run (`write-failed`); step 1 §9b, before any change (`context-rebuild-failed`); step 2 manifest write, in every mode (`manifest-write-failed`), or a purge that deleted nothing (`delete-failed`) |
| 5    | state-conflict       | step 1 §7 active-version guard; §3, §4 or §8b ownership guard (`not-skf-output`) |
| 6    | user-cancelled       | any interactive cancel or confirm-gate `[N]`; On-Activation headless-purge guard |

## Result Contract (Headless)

The single-line JSON contract every headless run of skf-drop-skill prints. The shared emitter, `shared/scripts/skf-emit-result-envelope.py`, builds each line from the payload the emitting step hands it and checks it against `shared/scripts/schemas/skf-drop-skill-result-envelope.v1.json`, so no stage types an envelope and a HALT prints the right shape whatever else is still in context.

When `{headless_mode}` is true, step 3 prints this envelope on **stdout** before chaining to step 4, a `--dry-run` prints it on **stdout** at the step 1 confirmation gate, and every HARD HALT prints it on **stderr** with `status: "error"`:

```
SKF_DROP_SKILL_RESULT_JSON: {"status":"success|error|dry-run","skill":"…|null","drop_mode":"…|null","versions_affected":[],"files_deleted":[],"would_delete":[],"forge_left_in_place":null,"manifest_updated":false,"result_path":null,"exit_code":0,"halt_reason":null,"error":null}
```

Field rules:

- `status`: `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow stopped at the confirmation gate before any change, `"error"` on any HALT.
- `halt_reason`: on success and dry-run it is `null`; otherwise one of `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-drop"`, `"active-version-guard-refused"`, `"not-skf-output"`, `"headless-purge-forbidden"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"delete-failed"`, `"write-failed"`, `"user-cancelled"`.
- `exit_code`: the emitter derives it from `halt_reason`, per the Exit Codes table above (`0` on success and dry-run).
- `skill`, `drop_mode`, `versions_affected`, `files_deleted`, `manifest_updated`: the values the emit site knows; a key not resolved yet takes the default shown in the template (`null`, `[]` or `false`). `versions_affected` is a list holding the one version dropped, or the string `"all"` for the whole skill.
- `would_delete`: in a dry run of a purge, the folders the purge would delete (the step 1 purge check's `affected_directories`), so an automator can check the blast radius before it runs the drop; `[]` otherwise, and in a dry run of a deprecate.
- `forge_left_in_place`: the forge folder a purge leaves in place (or, in a dry run, would leave) because SKF did not generate it; `null` otherwise.
- `result_path`: the per-run result file step 3 wrote, `{skills_output_folder}/drop-skill-result-{YYYYMMDD-HHmmss}.json` (UTC), stamped by the emitter; `null` for a dry run and a HALT, which write no result file.
- `error`: `null` on success and dry-run; on a HALT, `{"phase", "reason"}`, plus `path` when the halt names one: the step and gate that halted, and the halt message.
- `warnings`: present only when the run recorded at least one. A run that reports `success` can still carry the degraded outcomes step 2 records, which the report also shows: `context_rebuild_failed: <context file>: <error>` (a context file it could not rebuild), `active_link_dangling: <skill folder>/active: <manual fix>` (an `active` link a version purge left pointing at no version), `delete_failed: <path>: <error>` (a folder a partial purge could not delete) and `verification_failed: <what failed>: <manual fix>` (a final-state check that failed). Any run can carry `result_file_write_failed: <path>: <reason>` when the emitter could not write a result file, and `customization_resolver_unavailable: <reason>` when On Activation records that the customization resolver could not run, so the overrides under `{project-root}/_bmad/custom/` were not applied.

Each emit site supplies its `halt_reason`, `exit_code` and phase, and whichever discriminating fields it knows; the emitter fills in the rest.

## Halt Envelope

Every HALT names its exit code, `halt_reason` and phase where it stops. In headless mode it prints its envelope before it stops: it stages `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "exit_code": <code>}`, plus `"path"` when the halt names one and the envelope fields the site names, runs the first command below and displays the line it prints verbatim. The SKILL.md On-Activation run-folder halt has no folder to stage in, so it hands that payload, on one line, to the second command. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. The emitter gives every field the payload leaves out its default (`null`, `[]` or `false`) and checks `exit_code` against `halt_reason`. When the helper is missing, exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing; in step 1 or 2 it then deletes the run folder.

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill --target stderr <<'SKF_DROP_HALT'
{"phase": "on-activation:run-folder", "reason": "<the halt message>", "halt_reason": "write-failed", "exit_code": 4}
SKF_DROP_HALT
```

SKILL.md On-Activation §4 binds `{emitEnvelopeHelper}` and `{run_dir}`, and its HALTs follow this section. select.md and execute.md state the same rule in their section 1, so the HALTs of a step never depend on this file.

# Invocation Contract: skf-rename-skill

The inputs, flags, gate map, outputs and headless result envelope of `skf-rename-skill`. Interactive runs do not need this file; headless callers and pipeline integrators read it. `references/exit-codes.md` says where each exit code is raised.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `old_name` [required], `new_name` [required]. A supplied name answers its question in either mode: an interactive run asks only for a name that is missing, or again for one that fails its check. |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--dry-run` (run selection + validation + display the step 1 §8 confirmation block, then exit with `status="dry-run"`: no run lock, no copy, no manifest re-key, no delete, no result file); `--acknowledge-official` (answers the step 1 §6 source-authority warning for this run only, so a headless run may rename a skill whose `source_authority` is `"official"`; the decision is recorded in `headless_decisions[]`). |
| **Gates** | step 1: Input Gate [use args] x2 (§4 old name, §5 new name); Source-Authority Gate [Y/N] (§6, only for an `"official"` skill; headless default: HALT `source-authority-blocked` unless `--acknowledge-official` or the `force_source_authority_in_headless` setting); Confirm Gate [Y] (§8). Step 2 asks nothing. |
| **Outputs** | Renamed skill directories, updated manifest, updated context files, `{new_name}/rename-skill-result-{YYYYMMDD-HHmmss}.json` (UTC) and `{new_name}/rename-skill-result-latest.json`; a halt keeps its run folder under `{project-root}/_bmad-output/.skf-run/` |
| **Concurrency** | step 1 §4b takes the run lock `{forge_data_folder}/.skf-rename-{old_name}.lock` through `skf-run-lock.py`. While another rename of the same `old_name` holds a lock that has not gone stale (60 minutes after it was taken or renewed), the run HALTs with `halt_reason: "halted-for-concurrent-run"` (exit 5). Every exit releases it; `--dry-run` takes none. |
| **Headless** | All gates auto-resolve with their default action when `{headless_mode}` is true. The §6 source-authority warning HALTs by default when `source_authority="official"`: pass `--acknowledge-official` to proceed for one run. The `force_source_authority_in_headless = "true"` setting, in a team or personal override of this skill (SKILL.md On Activation step 3 names the files), is a standing approval for every headless run. Either way the decision is recorded in `headless_decisions[]`. |
| **Exit codes** | Stable per-failure-class codes: see `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 3 emits a single-line JSON envelope on **stdout** before chaining to step 4, the `--dry-run` exit (step 1 §8) emits it on **stdout** with `status: "dry-run"`, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`. The model never types the line: each site passes its payload to the shared emitter, `shared/scripts/skf-emit-result-envelope.py`, which checks it against `shared/scripts/schemas/skf-rename-skill-result-envelope.v1.json`:

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"success|error|dry-run","old_name":"…|null","new_name":"…|null","versions_renamed":[],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":0,"halt_reason":null,"headless_decisions":[],"run_id":"…","result_path":"…|null"}
```

`status` is `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited before step 1 §9 stores decisions, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-rename"`, `"not-skf-output"`, `"flat-layout"`, `"name-collision"`, `"source-authority-blocked"`, `"halted-for-concurrent-run"`, `"copy-failed"`, `"verify-failed"`, `"manifest-write-failed"`, `"write-failed"`, `"user-cancelled"`. (§7 context-file rebuild is best-effort and never halts, so it has no `halt_reason`.) `exit_code` matches `references/exit-codes.md`. `manifest_rekeyed` is true only when step 2 re-keyed an `exports.{old_name}` entry. `headless_decisions` is the audit trail of confirmation gates auto-resolved under `{headless_mode}`, each entry `{gate, default_action, taken_action, reason}` (the §6 source-authority decision, with `--acknowledge-official` or the setting as its reason, and the §8 auto-confirm); it is `[]` in interactive runs and whenever no gate was auto-resolved before the envelope was emitted. The schema describes the other fields: `versions_renamed`, `run_id`, `result_path`, a halt's `error` and the optional `warnings`.

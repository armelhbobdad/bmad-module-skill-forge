# Headless Contract

The exit codes and the result envelope of skf-audit-skill. Each stage's **Halt envelope** paragraph names the exit code, `halt_reason` and phase of every HALT in it and shows the emitter command that prints it.

## Exit Codes

Every hard halt in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                                          |
| ---- | -------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 0    | success              | step 7 (terminal health-check)                                                                                     |
| 2    | input-missing        | step 1 §1: no `skill_name` supplied in headless mode (interactive prompt cannot resolve)                           |
| 3    | resolution-failure   | On Activation (`uv`, or a helper the stages share, is missing → `helper-missing`); step 1 §1 (skill not found at resolved path: missing `SKILL.md` → `skill-not-found`; or a flat `SKILL.md` with no SKF marker in its `metadata.json` → `not-skf-output`); step 1 §2 (`forge-tier.yaml` missing: setup-forge not run → `forge-tier-missing`); step 1 §3 and §4 (the skill records nothing to audit against: a docs-only skill whose `doc_sources` records no hash, any other skill without a provenance map → `no-baseline`); step 1 §4, step 1c, step 3 §1 and, for a docs-only skill, step 5a (the provenance map or `doc_sources` cannot be read → `provenance-invalid`); step 1 §5 (source directory no longer exists / inaccessible → `source-dir-missing`); step 2 §3 (files the snapshot still lists to read after they were read by eye) and, for a docs-only skill, step 5a (no document could be compared: each failed to fetch or has no recorded hash) → `source-unreadable`; any step whose required helper resolves to no path or crashes → `helper-missing` |
| 4    | write-failure        | step 1 §6 / step 6 §4 (drift report write failed: read-only mount, disk full, permissions denied); step 1c, step 2 §2 and §3, step 3 §1 and step 5 §2 (a file in the stage data folder cannot be written); step 6's result contract (the emitter refuses the result payload twice) → `write-failed` |
| 6    | user-cancelled       | step 1 §1 manifest-vs-symlink gate `[X]` · step 1 §5b upstream-drift gate `[X]` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 prints one `SKF_AUDIT_RESULT_JSON: {...}` line on **stdout** before chaining to step 7, and every hard halt one on **stderr** with `status: "error"`. The shared emitter builds each line from the payload the stage stages in `{run_dir}`, folds in the decisions and warnings the run recorded there, stamps `run_id` and `result_path`, and checks it against `{project-root}/_bmad/skf/shared/scripts/schemas/skf-audit-result-envelope.v1.json` (`{project-root}/src/shared/scripts/schemas/skf-audit-result-envelope.v1.json` in a dev checkout), whose descriptions say what each field holds. Never type the line yourself:

```
SKF_AUDIT_RESULT_JSON: {"status":"success|error","skill_name":"…","drift_score":"CLEAN|MINOR|SIGNIFICANT|CRITICAL|null","report_path":"…|null","next_workflow":"update-skill|null","audit_ref":"…|null","upstream_moved":true|false|null,"upstream_ref":"…|null","exit_code":0,"halt_reason":null,"run_id":"…","result_path":"…|null"}
```

`next_workflow` is `"update-skill"` when CRITICAL or HIGH findings exist or when `upstream_moved` is true, otherwise `null`; pass `upstream_ref` to update-skill as `--target-ref`. `headless_decisions`, `warnings` and `error` appear when they apply. `halt_reason` is one of: `null` (success), `"input-missing"`, `"skill-not-found"`, `"not-skf-output"`, `"forge-tier-missing"`, `"no-baseline"`, `"source-dir-missing"`, `"provenance-invalid"`, `"source-unreadable"`, `"helper-missing"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

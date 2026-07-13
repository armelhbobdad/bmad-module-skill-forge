<!-- Config: communicate in {communication_language}. -->

# HARD HALT Contract

The exit-code map and error-result envelope every step emits on a HARD HALT. Any step loads this file on its failure path, so the wire format is available even if SKILL.md has been compacted mid-run.

## Exit Codes

Every HARD HALT in this workflow exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning                | Raised by                                                   |
| ---- | ---------------------- | ----------------------------------------------------------- |
| 0    | success                | step 7 (terminal)                                          |
| 3    | resolution-failure     | step 1 (prose input §2, registry chain §3, version-tag miss §3a, language abort §4); step 3 (non-library shape §1.5, zero-exports §4.5) |
| 4    | write-failure          | step 5 §2 (deliverable write failed)                       |
| 5    | overwrite-cancelled    | step 5 §1 (user selected [N])                              |
| 6    | user-cancelled         | step 1 §1 ([X] Cancel and exit, or cancel-line affordance); step 2 §3 ([A] Abort at ecosystem-match gate); step 4 §6 (user selected [Q]) |
| 7    | finalize-blocked       | step 6 §1 (active-pointer flip refused — non-link in place) |
| 8    | ecosystem-redirect     | step 2 §3 ([I] Install at ecosystem-match gate — user opted to install the existing official skill instead of compiling a custom community skill) |

## Result Contract on HARD HALT

In addition to the success-variant result contract written by step 6 §3, every HARD HALT must surface an **error variant** so headless automators don't silently break when `quick-skill-result-latest.json` is missing on failed runs.

**Always (every HARD HALT, regardless of phase)** — emit a single line on **stderr**:

```
SKF_QUICK_SKILL_RESULT_JSON: {"status":"error","exit_code":<N>,"phase":"<slug>","error":{"code":"<class>","message":"<short>"},"outputs":{},"summary":{},"skill_package":"<path-or-null>"}
```

One line, no pretty-print. Matches the prefix-and-envelope convention used by `skf-emit-result-envelope.py`.

**Additionally, when `{skill_package}` is known** (HALT at step 5 §1 onward) — write the same JSON object (without the `SKF_QUICK_SKILL_RESULT_JSON: ` prefix) to disk:

```
{skill_package}/quick-skill-result-{YYYYMMDD-HHmmss}.json
{skill_package}/quick-skill-result-latest.json   (copy, not symlink)
```

so consumers that hardcode the `-latest.json` path see a deterministic file even on failed runs. HALTs at step 1/02/03/04 cannot write to disk because `{skill_package}` is computed only in step 5 §1; for those, the stderr envelope plus exit code is the contract.

**Schema:**

| Field           | Type           | Notes                                                                                                       |
| --------------- | -------------- | ----------------------------------------------------------------------------------------------------------- |
| `status`        | string         | always `"error"` for HARD HALTs                                                                             |
| `exit_code`     | integer        | matches the Exit Codes table above                                                                          |
| `phase`         | string         | step slug where the HALT occurred (e.g. `resolve-target`, `compile`)                                        |
| `error.code`    | string         | one of: `resolution-failure`, `write-failure`, `overwrite-cancelled`, `user-cancelled`, `finalize-blocked`, `ecosystem-redirect` |
| `error.message` | string         | the user-facing message that was displayed                                                                  |
| `error.details` | any            | optional — phase-specific context (e.g. the failed file path)                                               |
| `outputs`       | object         | empty `{}` on early HALTs; partial when files were already written                                          |
| `summary`       | object         | empty `{}` on early HALTs                                                                                   |
| `skill_package` | string \| null | absolute path when known, `null` when HALT preceded step 5 §1                                              |

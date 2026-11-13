# Invocation Contract

The caller contract of Verify Stack: its inputs, flags, gates and outputs, and the result line a headless run prints.

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional], previous_report_path [optional] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--prd <path>` (skip step 1 prompt for the optional PRD); `--previous-report <path>` (skip step 1 prompt for delta comparison; `--previous-report none` runs without one); an interactive run still asks for another path when the one a flag gives is not found |
| **Gates** | step 1 Input Gate (use args), whose previous-report line offers the newest earlier report as its Enter default (headless default: use it; `none` skips the comparison). No later stage waits for input: a run with 0% coverage or only Blocked pairs prints one warning and continues, so its report still carries the recommendations. |
| **Outputs** | `feasibility-report-{project_slug}-{timestamp}.md` and its `feasibility-report-{project_slug}-latest.md` copy (not a symlink), written by step 6 once the finished report passes the feasibility-report check, both per the SKF shared feasibility report schema (`{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md`; `{project-root}/src/shared/references/feasibility-report-schema.md` in a dev checkout), with integration verdicts, coverage analysis, recommendations, and evidence sources; plus `verify-stack-result-{YYYYMMDD-HHmmss}.json` and `verify-stack-result-latest.json` in `{forge_data_folder}` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--prd`, `--previous-report`) consumed at the gates that would otherwise prompt. A `--prd` or `--previous-report` path that is not found does not halt: the run goes on without it and lists `prd_not_found: <path>` or `previous_report_not_found: <path>` in the envelope's `warnings`. A caller reads the run's own `SKF_VERIFY_STACK_RESULT_JSON` line. A run that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result, and `verify-stack-result-latest.json` may then describe an earlier run, so it is never read in its place. |
| **Exit codes** | See `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 prints one `SKF_VERIFY_STACK_RESULT_JSON: {...}` line on **stdout**, which the shared health check displays as the run's last line, and every HARD HALT one on **stderr**, built by the shared emitter: `references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command.

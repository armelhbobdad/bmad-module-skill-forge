# Headless Result Contract & Exit Codes

Canonical headless/pipeline contract for skf-analyze-source. Step files emit the envelope and exit with the codes defined here.

## Result Envelope

When `{headless_mode}` is true, step 6 (interactive) or step 1a (auto) emits a single-line JSON envelope on **stdout** before chaining to step 7. Every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`, using the exit code and `halt_reason` named at that HALT — so an automator branches on the failure class without grepping message text.

```
SKF_ANALYZE_RESULT_JSON: {"status":"success|error|redirect|skipped","report_path":"…|null","brief_paths":["…"],"unit_counts":{"confirmed":N,"skipped":N,"maybe":N},"exit_code":0,"halt_reason":null,"mode":"interactive|auto"}
```

- `status` — `"success"` on the terminal happy path, `"error"` on any HALT, `"redirect"` when coexistence routes to US (merge), `"skipped"` when the user skips a conflicting target.
- `halt_reason` — one of `null` (success), `"input-missing"`, `"resolution-failure"`, `"pin-invalid"`, `"write-failed"`, `"user-cancelled"`.
- `exit_code` — matches the table below.
- `report_path` — absolute path to the analysis report, or `null` on an early HALT.
- `brief_paths` — array of absolute paths to every generated `skill-brief.yaml` (empty array if none).
- `unit_counts` — `confirmed` (units approved for briefs) and `skipped` (rejected in step 5, or the skipped target in coexistence §0c) counts; auto mode reports `confirmed:N, skipped:0`. `maybe` is a reserved slot, currently always `0`.
- `mode` — `"auto"` when the `[auto]` flag was active, `"interactive"` otherwise.

In auto mode the envelope also carries `coexistence` (the §0c decision) and, when a pin resolves, `pinned_ref`/`pinned_version` — `step-auto-scope.md` §0b/§0c define those field semantics. The docs-only path adds `source_type: "docs-only"`.

## Exit Codes

Every HARD HALT exits with a stable code so headless automators can branch on the failure class.

| Code | Meaning | Raised by |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / skipped / redirect | step 7 (terminal — health check completion); coexistence `"skipped"`/`"redirect"` statuses from §0c |
| 2    | input-missing        | On Activation (config.yaml not loadable); step 1 §3 (project path empty/invalid in headless mode); step 1 §2b (auto mode without `--project-path`) |
| 3    | resolution-failure   | step 1 §2 (`forge-tier.yaml` missing at `{sidecar_path}/forge-tier.yaml`); step 1 §3 (project path does not exist or remote URL inaccessible); step 1a §0a (docs-only URL unreachable); step 1a §0b (`halt_reason: "pin-invalid"` when the supplied `--pin` matches no tag or branch); step 1a §3 (shape detection script error, exit code 2) |
| 4    | write-failed         | a failed write of the analysis report (step 1 §6 / step 1a §7 / §0a), a `skill-brief.yaml` (step 6 §5 / step 1a §8 / §0a), or the result contract (step 6 §9 / step 1a §10 / §0a) |
| 6    | user-cancelled       | any interactive menu in steps 2/3/5/6 (user selected `[X]` Cancel and exit) |

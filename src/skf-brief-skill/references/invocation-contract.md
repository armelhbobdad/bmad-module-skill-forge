# Invocation Contract — skf-brief-skill

Full argument set, gate map, exit codes, and headless result envelope for `skf-brief-skill`. Interactive callers can ignore this file; headless automators and pipeline integrators consult it. This is the canonical statement of the `from_brief` ratify contract — the source of truth for both the interactive (`gather-intent.md` §3.1a) and headless (step 1 §8 GATE) ratify paths.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `target_repo` [required], `skill_name` [required], `scope_hint` [optional], `language_hint` [optional], `target_version` [optional], `source_authority` [optional: official/community/internal, default community], `source_type` [optional: source/docs-only, default source], `doc_urls` [optional: list of `url[,label]` for source_type=docs-only or supplemental], `scope_type` [optional: full-library/specific-modules/public-api/component-library/reference-app/docs-only], `include` [optional: comma-separated globs], `exclude` [optional: comma-separated globs], `scripts_intent` [optional: detect/none/free-text, default detect], `assets_intent` [optional: detect/none/free-text, default detect], `intent` [optional: free-text used to derive description], `force` [optional: overwrite existing brief without prompting], `from_brief` [optional: path to a pre-authored `skill-brief.yaml` to *ratify* — when supplied it is the source of truth, `target_repo`/`skill_name` become optional/derived-from-brief, and the run mirrors the interactive §3.1a ratify path: schema-validate, skip analyze-target/scope-definition, write through the canonical writer in place], `[auto]` [optional: bracket modifier passed via pipeline context — when present, BS loads the upstream brief from `brief_path` in pipeline data, enriches it with doc detection, and writes through the canonical writer; requires `brief_path` from AN's `SKF_ANALYZE_RESULT_JSON`] |
| **Gates** | step 1: Input Gate [use args] | step 3: Confirm Gate [C] | step 4: Confirm Gate [C] |
| **Outputs** | `skill-brief.yaml` at `{forge_data_folder}/{skill-name}/skill-brief.yaml`; final `SKF_BRIEF_RESULT_JSON` line on stdout when `{headless_mode}` is true |
| **Headless** | All gates auto-resolve with heuristic-driven or default action when `{headless_mode}` is true; pre-supplied inputs consumed at the gates that would otherwise prompt; absent `source_authority` and `scope_type` are resolved by signal-driven detection (see `references/headless-args.md`); existing briefs are preserved unless `--force` was supplied (HALT with `overwrite-cancelled` otherwise); supplying `from_brief <path>` instead routes the step 1 GATE to the ratify path described in the `from_brief` Inputs cell (schema-validate, skip analyze/scope, write in place — no `--force` needed) rather than deriving a new brief |
| **Transient-failure retry** | This workflow does **not** auto-retry network or subprocess failures. A failed `gh` fetch (analyze-target.md §1, portfolio-similarity-check.md), QMD probe, or extraction script is logged and surfaced in the final result envelope as a warning, but the workflow continues with whatever signal it has. Headless pipelines that want retry semantics should wrap the invocation at their orchestrator level (e.g. CI re-runner on non-zero exit). Rationale: brief-skill is read-mostly with one terminal write (the YAML at step 5); a partial-signal retry has more failure modes than just re-running the whole workflow, which is cheap. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success              | step 6 (terminal)                                                                         |
| 2    | input-missing / input-invalid | step 1 GATE — required headless arg absent (`target_repo`, `skill_name`, or `doc_urls` when `source_type=docs-only`) → `input-missing`; enum violation, malformed semver, non-kebab `skill_name`, or step 5 brief-context schema validation failure → `input-invalid` |
| 3    | resolution-failure   | step 1 §1 (`forge-tier.yaml` missing); step 2 §1 (target inaccessible / `gh auth` fails) |
| 4    | write-failure        | step 1 §1 pre-flight write probe (data folder unwritable: read-only mount, disk full, permissions denied); step 5 §4 (write to `{forge_data_folder}/{skill-name}/skill-brief.yaml` failed) |
| 5    | overwrite-cancelled  | step 5 §2 (existing brief, `force` not supplied)                                          |
| 6    | user-cancelled       | any interactive menu in step 1/03/04 (user selected `[X]` Cancel and exit)                |

## Result Contract (Headless)

When `{headless_mode}` is true, step 5 emits a single-line JSON envelope on **stdout** before chaining to step 6, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_BRIEF_RESULT_JSON: {"status":"success|error","brief_path":"…|null","skill_name":"…","version":"…|null","language":"…|null","scope_type":"…|null","exit_code":0,"halt_reason":null,"mode":"auto|null"}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"forge-tier-missing"`, `"target-inaccessible"`, `"gh-auth-failed"`, `"write-failed"`, `"overwrite-cancelled"`, `"user-cancelled"`. `exit_code` matches the table above. `mode` is `"auto"` when BS was invoked with the `[auto]` flag (pipeline auto-brief generation), `null` otherwise (interactive or headless-without-auto).

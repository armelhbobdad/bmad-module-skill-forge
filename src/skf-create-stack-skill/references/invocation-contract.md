# Invocation Contract

The headless contract of Stack Skill: its inputs, gates and outputs, the exit code and `halt_reason` of every HARD HALT, and the result envelope. A halting step names its exit code, `halt_reason` and phase and shows the emit command, so it needs nothing else from this file.

| Aspect | Detail |
|--------|--------|
| **Inputs** | All optional; step 1 binds and checks each one, and halts with `input-invalid` on a value it cannot use. `project_path`: the folder code mode scans (default: the project root; an interactive run asks once when the manifests sit in several folders). `skills`: the libraries to rank, or the constituent skills in compose mode. `stack_name`: the stack's skill name (default `{project_name}-stack`). `scope_overrides`: step 3 scope overrides. `architecture_doc_path`: the document compose mode reads. `mode`: `code` or `compose` (default: step 1 detects it) |
| **Gates** | step 1: compose suggestion [accept] and scan scope [A] (each asked only in an interactive run; headless takes the default and records it); step 2: no manifest found (headless: HALT `no-manifests`, exit 2); step 3: scope gate [C]; step 6: review gate [C] |
| **Outputs** | SKILL.md (stack), context-snippet.md, metadata.json; `provenance-map.json` and `evidence-report.md` in `{forge_version}`; the result contract, `create-stack-skill-result-{YYYYMMDD-HHmmss}.json` and its `create-stack-skill-result-latest.json` copy in `{forge_version}`, with the `-latest` copy also at the stack group root `{forge_data_folder}/{stack_name}/`; a run folder under `{project-root}/_bmad-output/.skf-run/`, deleted when the run finishes or the user cancels and kept after any other HALT |
| **Headless** | All gates auto-resolve with their default action when `{headless_mode}` is true, and each records its decision in the run sink, so the envelope's `headless_decisions` lists every one |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by (halt_reason)                                                                     |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success              | step 10 (terminal handoff to shared health-check)                                          |
| 2    | input / precondition invalid | step 1 §0 `config.yaml` missing/malformed (`config-missing`); step 1 §0 or §3 an input it cannot use (`input-invalid`); step 2 §2 headless with no manifests (`no-manifests`, S2); step 4 §3 all extractions failed (`all-extractions-failed`, B7); step 5 §2 a feasibility report of another `schemaVersion` (`schema-version-mismatch`) or with a verdict token outside the schema's set (`unknown-verdict-token`) |
| 3    | resolution-failure   | step 1 §1 `forge-tier.yaml` missing (`forge-tier-missing`); a shared helper that resolves to no path (`helper-missing`): `skf-emit-result-envelope.py` (step 1 pre-flight), `skf-validate-frontmatter.py` (step 1 §0), `skf-scan-manifests.py` or `skf-enumerate-stack-skills.py` (step 1 §3, step 2 §0 and §2, step 4 §0), `skf-count-imports.py` (step 3 §1), `skf-render-stack-metadata.py` (step 4 §3a, step 5 §3, step 6 §1, step 7 §6), `skf-pair-intersect.py` (step 5 §1), `skf-comention-pairs.py` (step 5 §2), `skf-atomic-write.py` (step 7 §1); step 2 §0 compose-mode stale manifest (a manifest key whose skill folder is gone) or zero qualifying skills (S1/B4), step 4 §0 compose cycle among confirmed skills or a confirmed skill no longer an SKF package (`resolution-failure`) |
| 4    | write-failure        | step 1 pre-flight: the run folder cannot be created; step 7: a stage-dir, write or commit-dir failure (the §1 rollback contract), or a group-dir collision when an existing non-stack skill occupies the target path (`write-failure`) |
| 5    | state-conflict       | step 7 §1 ownership check (S3, both phases): the stack's folder in skills_output_folder, or the version folder this run writes, is not SKF output or SKF cannot check it (`not-skf-output`); an SKF stack still in the flat layout (`flat-layout`) |
| 6    | user-cancelled       | step 2 §2 option 3 (no manifests, interactive); `[X]` Cancel and exit at the step 3 scope gate or the step 6 review gate (`user-cancelled`) |

## Result Contract (Headless)

The shared emitter, `skf-emit-result-envelope.py`, builds every `SKF_STACK_RESULT_JSON: {...}` line from the payload a step stages in `{run_dir}`, folds in the decisions and warnings the run recorded there, derives `exit_code` from `halt_reason`, stamps `run_id` and `result_path`, and checks the line against `shared/scripts/schemas/skf-stack-result-envelope.v1.json` (installed under `{project-root}/_bmad/skf/`), whose descriptions say what each field holds. Never type the line yourself. Every HARD HALT prints one on **stderr**, in every mode, with `status: "error"`, except the `init:emitter` halt, which has no emitter to print one; step 9 prints the success line on **stdout** and displays it when `{headless_mode}` is true, before chaining to step 10:

```
SKF_STACK_RESULT_JSON: {"status":"success|error","skill_package":"...|null","skill_name":"...","stack_libraries":["..."],"mode":"code|compose","quality_score":null,"exit_code":0,"halt_reason":null,"run_id":"...","result_path":"...|null","headless_decisions":[],"warnings":[]}
```

A halt adds `error`: its `phase`, its message as `reason`, and `path` when it names a file or folder. When the customization resolver could not run, `warnings` holds `[activation/warn] customization_resolver_unavailable: <reason>`, which step 1 records before any other warning: the run used the bundled `customize.toml` alone, without the `{project-root}/_bmad/custom/` overrides.

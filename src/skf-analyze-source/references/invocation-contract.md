<!-- Config: communicate in {communication_language}. -->

# Invocation Contract: skf-analyze-source

The inputs, flags, gates, outputs and exit codes of `skf-analyze-source`, for headless callers and pipelines; interactive runs do not need this file.

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], intent_hint, scope_hint, target_ref or target_refs [optional]. `project_path` is a repository URL or a local path, or in `[auto]` mode a documentation URL (routed docs-only). An interactive run reads them from the invocation and asks at most one opening question. |
| **Headless inputs** | `--project-path <path>` (comma-separated for several; one for `[auto]`), `--scope-hint <text>` (folders or packages to focus on or skip, `[auto]` included), `--intent-hint <text>` (the goal: ranks the step 5 recommendations; an interactive run also defers the units outside it, a headless run never), `--target-ref <ref>` (a tag or branch for every project path, written into every brief; not `[auto]`, which pins with `--pin`), `--target-refs <path:ref,...>` (one ref per path, written into each unit's brief; not with `--target-ref`, and not `[auto]`), `--pin <version>` (`[auto]` only: a tag or branch; absent, the latest release tag; a step-by-step analysis an `[auto]` run falls back to keeps its pin) |
| **Headless flag** | `--headless` / `-H` flips every confirm gate to auto-proceed |
| **Auto flag** | `[auto]` bracket modifier: activates auto-scope mode (step 1a; see SKILL.md's **Auto mode path**). Pipelines pass this as `AN[auto]`. Requires `--project-path` naming one target. |
| **Gates** | one per step: steps 2 to 4 [C] (step 4 also takes composite merges, default accept); step 5 [C] after the decisions (default: confirm every card, flag every stack skill candidate); step 6 [Y] (write briefs). Headless takes each default and records it in `headless_decisions`. Auto mode: only the step 1a coexistence gate (default [A]longside) |
| **Outputs** | analysis-report.md (and, in a step-by-step analysis, the units file `analyze-source-units-{project_name}.json` beside it), skill-brief.yaml files (one per recommended unit) and the run's result files, written by every run that ends, zero confirmed units included; final `SKF_ANALYZE_RESULT_JSON` line on stdout when `{headless_mode}` is true. In auto mode, the envelope includes `"mode":"auto"`. |
| **Exit codes** | Envelope, emitter, result files, `halt_reason` enum and exit codes: `references/headless-contract.md` |

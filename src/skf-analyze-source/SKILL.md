---
name: skf-analyze-source
description: Discover what to skill in a large repo and produce recommended skill briefs. Use when the user requests to "analyze source for skills" or "discover skill opportunities."
---

# Analyze Source

## Overview

Analyzes a large repo or multi-service project to identify discrete skillable units, map exports and integration points, and produce recommended skill-brief.yaml files as the primary entry point for brownfield onboarding. The analysis must be thorough enough to produce actionable briefs, but scoped enough to avoid overwhelming the user with false positives. Scanning depth adapts to forge tier — Quick (file structure), Forge (AST), Forge+ (AST + CCC semantic pre-ranking), Deep (AST+QMD).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a source code analyst and decomposition architect collaborating with a developer onboarding an existing project. You bring expertise in codebase analysis, service boundary detection, and skill scoping, while the user brings their domain knowledge. Work together as equals.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}` (the language for user-facing prose). Written artifact text — the per-unit recommendation `description` and `scope.notes` persisted into `skill-brief.yaml` — is in `{document_output_language}`; per-step rules call this out where it applies. The two values may be the same.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed | Condition |
|---|------|------|--------------|-----------|
| 1 | Initialize | references/init.md | Yes | Always |
| 1a | Auto-Scope | references/step-auto-scope.md | Yes | `[auto]` mode only. Includes §0b pin resolution — validates and resolves version pin before scoping. Includes §0c coexistence detection — checks for existing skills before proceeding. Includes §0 docs-only URL detection — doc URLs short-circuit auto-scope entirely |
| 1b | Continue (session resume) | references/continue.md | Yes | Always |
| 2 | Scan Project | references/scan-project.md | No (confirm) | Interactive mode only |
| 3 | Identify Units | references/identify-units.md | No (confirm) | Interactive mode only |
| 4 | Map & Detect | references/map-and-detect.md | Yes | Interactive mode only |
| 5 | Recommend | references/recommend.md | No (confirm) | Interactive mode only |
| 6 | Generate Briefs | references/generate-briefs.md | Yes | Interactive mode only |
| 7 | Workflow Health Check | references/health-check.md | Yes | Always |

**Auto mode path:** When `[auto]` flag is present, init (step 1) routes directly to step 1a, which performs manifest scan → shape detection → scope generation → brief write → health check, bypassing steps 2–6. After URL type detection (§0), pin resolution (§0b) validates the `--pin` argument (or resolves the latest release tag) and stores the resolved ref for downstream brief writes. Coexistence detection (§0c) then checks for existing skills matching the target. If found, the user chooses alongside/merge/skip. Headless mode auto-selects alongside. Auto-scope may produce N > 1 confirmed units when a monorepo crosses the decomposition threshold (`package_count > 3`) **and** the §3b cohesion check decides to split, resulting in N briefs and N `brief_paths` in the envelope; a cohesive monorepo merges to one skill instead. A single large library is never decomposed — its size is handled by `skf-create-skill`'s auto-shard. When the target is a documentation URL (not a GitHub repo or local path), auto-scope detects the docs-only input at §0, validates URL reachability, writes a docs-only brief, and emits the envelope without performing source analysis.

**Shape detection reference:** `references/step-shape-detect.md` — loaded by step 1a as a reference doc (not a chained step).

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], scope_hint [optional]. `project_path` can be a GitHub repo URL, a local filesystem path, or a documentation URL for docs-only mode. The URL type heuristic at §0 determines the mode. |
| **Headless inputs** | `--project-path <path>` (skip Step 1 project-path prompt; accepts documentation URLs for docs-only mode), `--scope-hint <text>` (skip Step 1 scope-hint prompt), `--intent-hint <text>` (pre-supply analysis intent; drives recommendation ranking in Step 5), `--pin <version>` (pin to a specific version tag or branch; accepts semver tags, git tags, and branch names; when absent, resolves to the latest release tag) |
| **Headless flag** | `--headless` / `-H` flips every confirm gate to auto-proceed |
| **Auto flag** | `[auto]` bracket modifier — activates auto-scope mode (step 1a). Pipelines pass this as `AN[auto]`. When active, init routes to `step-auto-scope.md` which performs shape detection → scope generation → brief write, bypassing interactive steps 2–6. Requires `--project-path`. |
| **Gates** | step 2: Confirm Gate [C] | step 3: Confirm Gate [C] | step 5: Confirm Gate [C] (all skipped in auto mode) |
| **Outputs** | analysis-report.md, skill-brief.yaml files (one per recommended unit); final `SKF_ANALYZE_RESULT_JSON` line on stdout when `{headless_mode}` is true. In auto mode, the envelope includes `"mode":"auto"`. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / skipped / redirect | step 7 (terminal — health check completion); also covers coexistence `"skipped"` and `"redirect"` statuses from §0c |
| 2    | input-missing        | step 1 §2-3 — required config absent (config.yaml not loadable, project path empty/invalid in headless mode); step 1 §2b — auto mode without `--project-path` |
| 3    | resolution-failure   | step 1 §2 (`forge-tier.yaml` missing at `{sidecar_path}/forge-tier.yaml`); step 1 §3 (project path does not exist or remote URL inaccessible); step 1a §0a (docs-only URL unreachable); step 1a §0b (pin validation failure — `halt_reason: "pin-invalid"` when the supplied `--pin` does not match any tag or branch); step 1a §3 (shape detection script error, exit code 2) |
| 4    | write-failure        | step 1 §6 (analysis report write failed); step 6 §5 (skill-brief.yaml write failed); step 6 §9 (result contract write failed) |
| 6    | user-cancelled       | any interactive menu in steps 2/3/5/6 (user selected `[X]` Cancel and exit)               |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 (interactive) or step 1a (auto) emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_ANALYZE_RESULT_JSON: {"status":"success|error","report_path":"…|null","brief_paths":["…"],"unit_counts":{"confirmed":N,"skipped":N,"maybe":N},"exit_code":0,"halt_reason":null,"mode":"interactive|auto"}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT, `"redirect"` when coexistence detection routes to US (merge), or `"skipped"` when the user skips a conflicting target. `halt_reason` is one of: `null` (success), `"input-missing"`, `"forge-tier-missing"`, `"path-invalid"`, `"pin-invalid"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above. `brief_paths` is an array of absolute paths to every generated `skill-brief.yaml` (empty array if none were generated). `unit_counts` reports confirmed/skipped/maybe counts from step 5's user decisions. `mode` is `"auto"` when the `[auto]` flag was active, `"interactive"` otherwise (omitting `mode` is equivalent to `"interactive"` for backward compatibility). The `coexistence` field (present when §0c triggers) is `"alongside"`, `"merge"`, or `"skip"`, indicating the user's coexistence decision. The `pinned_ref` and `pinned_version` fields (present when §0b resolves a pin) record the resolved git ref and extracted semver version for provenance tracking.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `skills_output_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{unitDetectionHeuristicsPath}` ← `workflow.unit_detection_heuristics_path` if non-empty, else `references/unit-detection-heuristics.md`
   - `{briefSchemaPath}` ← `workflow.brief_schema_path` if non-empty, else `assets/skill-brief-schema.md`
   - `{analysisReportTemplatePath}` ← `workflow.analysis_report_template_path` if non-empty, else `templates/analysis-report-template.md`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — workflow skips the hook invocation)

   Stash all four as workflow-context variables. Stage files reference `{unitDetectionHeuristicsPath}` / `{briefSchemaPath}` / `{analysisReportTemplatePath}` / `{onCompleteCommand}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies (or wire in pipeline hooks) without forking the skill.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.

---
nextStepFile: 'rank-and-confirm.md'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runFile: '{run_dir}/run.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Set the Compose Scope

## STEP GOAL:

Set the recommended scope from the skills step 2 picked and show it by architectural layer, for the scope gate of `references/rank-and-confirm.md` §3.

## Rules

- Do not confirm the scope here: the gate does

## MANDATORY SEQUENCE

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

### 1. Set the Recommended Scope

Skip import counting entirely. All skills are included by default: the recommended scope is every `raw_dependencies` entry (the list step 2 stored).

**Apply scope_overrides:** If `scope_overrides` were provided in step 01, apply them now: force-include or force-exclude skills as specified. Log any overrides applied.

**Validate override keys:** Every key in `scope_overrides` MUST be present in `raw_dependencies`. For any unknown key, append a `workflow_warnings[]` entry (`step: "step-03"`, `severity: "warn"`, `code: "scope-override-unknown"`, `message`: "scope_override: unknown dependency '{key}', skipped") and drop that override entry (do not fail the run). Known-key overrides still apply.

Present skills sorted by architectural layer (from architecture doc if available):
- If `architecture_doc_path` is not null: **wrap the architecture-doc parse in try/except**. On any parse error (file unreadable, malformed markdown, no H2 structure), fall back to alphabetical ordering and log a warning `"architecture-doc parse failed: {error}; falling back to alphabetical"`. Otherwise parse section headers to determine layer grouping.
- If `architecture_doc_path` is null or layers not detectable: present alphabetically.

Display skills as a table, with the Published column only on a rerun (`{prior_libraries}` set; read it from `{runFile}` if lost): `kept` for a skill of `{prior_libraries}`, `new` for any other:

| # | Skill | Language | Tier | Architecture Layer | Published |
|---|-------|----------|------|--------------------|-----------|
| 1 | {name} | {language} | {confidence_tier} | {layer or 'Unclassified'} | {kept or new} |

Set `confirmed_dependencies` ← that scope, with the overrides applied.

### 2. Go to the Scope Gate

Load, read the full file and then execute `{nextStepFile}`: its §1 sends a compose run to its gate.

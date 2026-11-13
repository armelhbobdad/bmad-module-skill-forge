---
nextStepFile: 'rank-and-confirm.md'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runFile: '{run_dir}/run.json'
scopeFile: '{run_dir}/scope.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Set the Compose Scope

## STEP GOAL:

Set the recommended scope from the skills step 2 picked and show it by architectural layer, for the scope gate of `references/rank-and-confirm.md` §3.

## Rules

- Do not confirm the scope here: the gate does
- Take the scope from `skf-count-imports.py scope` and each skill's layer candidates from `skf-comention-pairs.py mentions`; never work either out by hand

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "compose"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

### 1. Set the Recommended Scope

No import is counted: every skill step 2 picked is in scope unless `scope_overrides` excludes it. **Resolve `{countImportsHelper}`** from `{countImportsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `compose-scope:scope`) with "**Cannot proceed.** `skf-count-imports.py` is missing, so the compose scope cannot be set. Re-install SKF, then re-run."

Pipe the names of `raw_dependencies` (the skills step 2 stored) on stdin as a JSON array. Pass the first bracketed flag only when `scope_overrides` is set, after writing it as JSON to `{run_dir}/scope-overrides.json` with a file write, and the second group only on a rerun (`{prior_libraries}` set; read it and `{prior_stack_version}` from `{runFile}` if lost), with the published libraries comma-separated:

```bash
uv run {countImportsHelper} scope --names - [--overrides "{run_dir}/scope-overrides.json"] [--prior-version "{prior_stack_version}" --prior-libraries "{prior_libraries}"] > "{scopeFile}"
```

A non-zero exit means the call is malformed: fix it and run it again. `{scopeFile}` holds what the scope gate shows and records: `scope`, the skills in; `dropped`, each skill left out with its `reason` (a published one's led by `in v{prior_stack_version}: `); `prior_kept`, always `[]` here; and `unknown_overrides`, the `scope_overrides` keys that name no skill step 2 picked, which the helper skips. Append one `workflow_warnings[]` entry per `unknown_overrides[]` key (`step: "step-03"`, `severity: "warn"`, `code: "scope-override-unknown"`, `message`: "scope_override: unknown dependency '{key}', skipped"); an unknown key never halts the run.

**Layers.** When `architecture_doc_path` is set, resolve `{comentionHelper}` from `{comentionProbeOrder}` (first existing path wins) and pipe the `raw_dependencies` names on stdin as a JSON array, so a skill the user adds at the gate has its layer too:

```bash
uv run {comentionHelper} mentions --doc "{architecture_doc_path}" --skills -
```

A skill's layer candidates are the non-null `paragraphs[].header` values of its `skills[]` entry. Its layer is its one candidate or, among several, the one that names a layer of the stack (a header such as `Frontend`, not `Overview`); a skill with none is `Unclassified`. When no candidate path exists or the call exits non-zero, list the skills by name and append a `workflow_warnings[]` entry (`step: "step-03"`, `severity: "warn"`, `code: "architecture-doc-parse-failed"`, `message`: "architecture-doc parse failed: {the helper's error, or that it is missing}; listing skills by name"). With no `architecture_doc_path`, or a document whose paragraphs have no header, list the skills by name, with no warning.

Display the `scope` skills as a table grouped by layer, the layers in the order the document first names them and `Unclassified` last, by name within a layer, with the Published column only on a rerun (`{prior_libraries}` set; read it from `{runFile}` if lost): `kept` for a skill of `{prior_libraries}`, `new` for any other:

| # | Skill | Language | Tier | Architecture Layer | Published |
|---|-------|----------|------|--------------------|-----------|
| 1 | {name} | {language} | {confidence_tier} | {layer or 'Unclassified'} | {kept or new} |

Set `confirmed_dependencies` ← `{scopeFile}`'s `scope`.

### 2. Go to the Scope Gate

Load, read the full file and then execute `{nextStepFile}`: its §1 sends a compose run to its gate.

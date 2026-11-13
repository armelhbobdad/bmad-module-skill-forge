---
nextStepFile: 'detect-manifests.md'
composeNextStepFile: 'compose-skills.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
runFile: '{run_dir}/run.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize

## STEP GOAL:

Load forge tier configuration, validate prerequisites, check the stack's folder and read the stack a rerun builds on, bind and check the invocation inputs, and choose the mode and the folder code mode scans.

## Rules

- Focus on configuration, prerequisites, inputs and the mode: the two helper runs of §3 only decide the mode and the scan scope, and ranking dependencies is step 3's work

## MANDATORY SEQUENCE

**Pre-flight: the emitter and the run folder.** Both come first, so every later HALT can emit its envelope. Resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}`; first existing path wins. It builds every `SKF_STACK_RESULT_JSON` line and the result files, and records each warning and auto-decision, so it stays bound for the whole run. If neither path exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `init:emitter`) and display only: "**Cannot proceed.** `skf-emit-result-envelope.py` is missing, so no result envelope can be built. Re-install SKF, then re-run." Then create the run folder:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-create-stack-skill-XXXXXXXX"
```

Bind `{run_dir}` ← the path it prints: the run's state lives there until step 9 deletes it. If the command fails, HALT (exit 4, `halt_reason: "write-failure"`, phase `init:run-folder`): "**Cannot proceed.** The run folder could not be created: {the first stderr line}." With no folder to stage in, emit with the payload on stdin:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --target stderr <<'SKF_JSON'
{"phase": "init:run-folder", "halt_reason": "write-failure", "reason": "<the halt message, one line>"}
SKF_JSON
```

**Halt envelope.** Every later HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}"}`, leaving out `skill_name` before §0 binds `{stack_name}` and adding `"path"` when the halt names a file or folder, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

**Resolver warning.** When SKILL.md On Activation bound `{customization_resolver_unavailable}` (the customization resolver could not run, so the `{project-root}/_bmad/custom/` overrides do not apply), record it now, as the run's first warning: write `[activation/warn] customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/warning.txt` with a file write, never an `echo` or a quoted `--warning` argument (a resolver error can hold quotes or `$( )`), then run the `record` command above.

### 0. Validate Project Config

Load `{project-root}/_bmad/skf/config.yaml`. If the file is missing OR fails YAML parse OR lacks the required top-level keys (`project_name`, `output_folder`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`), HALT with:

"**Cannot proceed.** SKF is not initialized for this project (config.yaml missing or malformed).

**Required:** Run `skf init` first.

**Halting workflow.**"

That is a HALT (exit 2, `halt_reason: "config-missing"`, phase `init:config`), emitted per the halt envelope above with no `skill_name`: `project_name` is unresolved here.

**Stack name.** Every later envelope and path names the stack, so bind `{stack_name}` now: the `stack_name` input, with `-stack` appended when it does not already end in it (`acme-web` gives `acme-web-stack`), else `{project_name}-stack`. When the input was given, check the bound name with the name rule step 7's pre-commit check applies to the stack's folder. Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `init:stack-name`, no `skill_name`) with "**Cannot proceed.** `skf-validate-frontmatter.py` is missing, so SKF cannot check `stack_name`. Re-install SKF, then re-run." Otherwise run:

```bash
uv run {frontmatterValidator} --check-name {stack_name}
```

On exit `1` (a name over 64 characters, two hyphens in a row, an upper-case letter or another character the rule refuses), HALT (exit 2, `halt_reason: "input-invalid"`, phase `init:stack-name`, no `skill_name`: the name was refused) with "**Cannot proceed.** `stack_name` `{value}` gives `{stack_name}`, which is not a skill name: {each `issues[]` message}. Fix the input and re-run."

**Ownership, phase 1.** Before any prior metadata is read or any import counted, check the stack's folder, `{skill_group}` (`{skills_output_folder}/{stack_name}/`): resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}`; first existing path wins. Run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --forge-data-folder {forge_data_folder}
```

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder`, `{write_detail}` ← `write_check.detail` and `{prior_active_version}` ← `write_check.marked_active_version`, and apply the ownership refusals below. When `{prior_active_version}` is not null, read `{skills_output_folder}/{stack_name}/{prior_active_version}/{stack_name}/metadata.json`: a `skill_type` other than `"stack"` is a HALT (exit 4, `halt_reason: "write-failure"`, phase `init:not-a-stack`, `path` `{skill_group}`) with "**Cannot proceed.** `{skills_output_folder}/{stack_name}/` exists but is not a stack skill (`skill_type={found_type}`). Rename the existing directory or pass another `stack_name` to avoid collision." Otherwise this run reruns the published stack: bind `{prior_stack_version}` ← its `version` and `{prior_libraries}` ← its `libraries`, which step 3 marks the scope against and step 7 versions a compose-mode re-composition from. A new stack leaves all three `null`.

**Ownership refusals.** Continue only when the status is `ok` and `{write_verdict}` is `"ok"`, or, when no helper candidate resolves, only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise create nothing and refuse with "**`{stack_name}`: nothing was written.** {clause}", taking the clause of the first case that applies:

- `{write_verdict}` is `"flat-layout"`: "It still uses the flat layout: a version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {stack_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"`: "It is not SKF output: `{write_folder}` {write_detail}, so SKF writes no version there. {remedy}"
- The status is not `ok`, or the output has no `write_check` (an older helper with no `--write-check` reports a new skill as `SKILL_NOT_FOUND`): "SKF could not check who generated it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date). {remedy}"
- No helper candidate resolved: "SKF cannot check who generated it: `skf-skill-inventory.py` is missing; re-install SKF. {remedy}"

`{remedy}` is "A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{stack_name}` yourself and pass another `stack_name` for this stack. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder without `metadata.json` may be an interrupted run's: delete it yourself."

Each refusal is a HARD HALT (exit 5, `halt_reason: "not-skf-output"`, or `halt_reason: "flat-layout"` for the flat-layout refusal, phase `init:ownership`, `path` `{write_folder}`, or `{skill_group}` when no helper candidate resolved): stop here, before any import is counted.

### 0b. Offer to Resume at the Review Gate

Only an interactive run looks for an earlier run: a headless run always starts fresh. Read each `{project-root}/_bmad-output/.skf-run/skf-create-stack-skill-*/run.json` and keep each folder whose `run.json` parses, names this `{stack_name}` and holds `headless_mode` false, and that holds a `draft/SKILL.md` changed after `{forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json` was written, when that file exists (a run that finished this stack since then replaced that draft). With none, go on to §1. Otherwise offer the one whose `draft/SKILL.md` changed last:

"**An interrupted run left a draft of `{stack_name}` for review** (last changed: {that file's modification time}).
  [Y] Resume at the review of that draft
  [N] Start fresh (that run folder stays as it is: {its path})"

- **[Y]:** delete this run's new folder, the one the pre-flight created (it holds at most the resolver warning), bind `{run_dir}` to the found folder and restore every binding its `run.json` holds, the earlier run's template paths and hook among them, since they built the draft. Set `{resumed_at_review}` true and, when On Activation bound `{customization_resolver_unavailable}`, record it in that folder as the resolver warning above does. Then load, read the full file and execute `references/compile-stack.md`, which goes straight to the review of the draft.
- **[N]:** leave the found folder as it is and go on to §1 in this run's own folder.

### 1. Load Forge Tier Configuration

Load `{forgeTierFile}` from the Ferris sidecar.

**If forge-tier.yaml does not exist:**

"**Cannot proceed.** The setup workflow has not been run for this project.

**Required:** Run `setup` first to detect available tools and determine your forge tier.

**Halting workflow.**"

That is a HALT (exit 3, `halt_reason: "forge-tier-missing"`, phase `init:forge-tier`, `path` `{forgeTierFile}`), emitted per the halt envelope above.

**If forge-tier.yaml exists:**

Extract:
- `forge_tier` — Quick, Forge, Forge+, or Deep
- `available_tools` — list of detected tools (gh_bridge, ast_bridge, qmd_bridge, skill-check)
- `project_root` — project root path

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

### 2. Validate Available Tools

**Tier-dependent tools:**
- **Forge:** ast_bridge (ast-grep structural analysis) — required for Forge tier
- **Forge+:** ast_bridge + ccc_bridge (CCC semantic search, which step 5 uses to pick the files that best show each integration)
- **Deep:** qmd_bridge (QMD temporal enrichment) — required for Deep tier

See `knowledge/tool-resolution.md` for how each bridge name resolves to concrete tools per IDE environment.

Report tool availability. If a tier-required tool is missing, downgrade tier and note:

"**Tier adjusted:** {original_tier} → {adjusted_tier} — {missing_tool} unavailable."

### 3. Bind Inputs and Choose the Mode

**Inputs.** Bind each input the invocation gives (`references/invocation-contract.md` lists them; `stack_name` is bound in §0), and check them all before the first question below:

- `skills` → `explicit_deps`: a value that names an existing file is a list, one name per line; any other value is comma-separated names. In code mode they are the libraries to rank, and step 2 skips the manifest scan; in compose mode they are the constituent skills, each a skill folder name or a package path, which step 2's helper reduces to its skill folder.
- `scope_overrides` → `scope_overrides`: `name: include` or `name: exclude` entries, which step 3 applies.
- `architecture_doc_path` → `architecture_doc_path`: the document compose mode maps integrations from.
- `mode` → `code` or `compose`.
- `project_path` → `{scan_root}` (below).

A `mode` other than `code` or `compose`, a `scope_overrides` value other than `include` or `exclude`, a `skills` list file that cannot be read, an `architecture_doc_path` that is not a readable file, or a `project_path` that is not a folder HALTs (exit 2, `halt_reason: "input-invalid"`, phase `init:inputs`) with "**Cannot proceed.** `{input}`: {why}. Fix the input and re-run."

**Scan root.** `{scan_root}` is the folder code mode reads: step 2 scans its manifests, step 3 counts the imports in it, and step 5 pairs libraries by those counts. It is `project_path` when given (a relative path resolves from `project_root`), else `project_root`. Compose mode reads no source code, so it never uses `{scan_root}`: a `project_path` given to a compose-mode run is not read, and the run appends `{step: "step-01", severity: "warn", code: "project-path-ignored", message: "compose mode reads no source code: project_path not read"}` to `workflow_warnings[]`.

**Mode.** The first rule that applies sets `compose_mode`:

1. `mode` is `compose`: `compose_mode: true`.
2. `mode` is `code`: `compose_mode: false`. An `architecture_doc_path` given with it is not read: append `{step: "step-01", severity: "warn", code: "architecture-doc-ignored", message: "mode code reads no architecture document"}` to `workflow_warnings[]`.
3. `architecture_doc_path` was given: `compose_mode: true`.
4. Otherwise two helpers decide. Resolve `{scanManifestsHelper}` from `{scanManifestsProbeOrder}` and `{enumerateStackSkillsHelper}` from `{enumerateStackSkillsProbeOrder}`; first existing path wins. When one has no candidate, HALT (exit 3, `halt_reason: "helper-missing"`, phase `init:mode`) with "**Cannot proceed.** `{script}` is missing, so SKF cannot choose the mode. Re-install SKF, then re-run." Scan `{scan_root}` and keep the JSON as `{manifest_scan}`, which step 2 reuses:

   ```bash
   uv run {scanManifestsHelper} scan {scan_root} --include-dev
   ```

   When its `manifests` is empty, list the skills compose mode could build from, passing `--explicit` with the `explicit_deps` entries as given, comma-separated, when this section bound them, and keep the JSON as `{skill_candidates}`, which step 2 reuses (an exit `1`, no skills folder, means none):

   ```bash
   uv run {enumerateStackSkillsHelper} candidates {skills_output_folder} [--explicit "<names>"]
   ```

   When its `kept[]` is not empty, suggest compose mode, naming its `{N}` skills, and ask for an optional architecture document path (ask again for a path that is not a readable file). If the user accepts, set `compose_mode: true` and store `architecture_doc_path` (`null` when the user gives none); if the user declines, code mode stays. In every other case the run uses code mode: step 2 ranks `explicit_deps` when given.

   **GATE [default: accept]**, headless default: do NOT prompt: accept the suggestion (`compose_mode: true`, `architecture_doc_path: null`). With no manifests, code mode would only halt at step 2 (`no-manifests`) or rank `explicit_deps` in a tree that declares none of them, while `kept[]` holds SKF skills (those `explicit_deps` names, when given): compose is the path that produces the stack. Record the auto-decision: stage `{"gate": "init.compose-suggestion", "default_action": "accept", "taken_action": "accept", "reason": "headless: no manifests and {N} SKF skills, so compose mode", "evidence": {"discoverable_skills": {N}}}` as `{run_dir}/decision.json` and run:

   ```bash
   uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
   ```

**Scan scope (code mode).** Run the scan call above (resolving `{scanManifestsHelper}` as rule 4 does) when rule 2 set the mode, so `{manifest_scan}` holds the scan of `{scan_root}`. When its `folders[]` lists more than one folder and no `project_path` was given, ask once which folder the stack covers:

"**This project holds several packages.** Type **A** to build the stack for the whole project (the default), or the folder of one package: {each `folders[]` entry's `path`, with its `names`}."

A folder answer resolves from `project_root`. When it is no folder, ask again; otherwise set `{scan_root}` to it and run the scan call again, replacing `{manifest_scan}`. **GATE [default: A]**: headless, do not ask; keep the project root, record the auto-decision as the compose-suggestion gate above does, with `{"gate": "init.scan-root", "default_action": "A", "taken_action": "A", "reason": "headless: manifests in {N} folders, so the whole project; pass project_path to scan one package", "evidence": {"folders": {N}}}`, `{N}` being the `folders[]` count: its `reason` tells the user to pass `project_path`.

Skills use version-nested directories: see `knowledge/version-paths.md` for the path templates.

If compose_mode:
- Display: "**Compose mode detected.** Synthesizing stack skill from existing skills + architecture document."

### 4. Display Initialization Summary

Report that the Stack Skill Forge is initialized, naming: the project (`{project_name}`); the forge tier (`{forge_tier}`) with its positive-capability framing (Quick = source reading and import counting; Forge = AST-backed structural analysis; Forge+ = AST structural + CCC semantic search for the files that show each integration; Deep = full intelligence: structural + contextual + temporal); the available tools (`{tool_list}`); the stack name (`{stack_name}`) and, on a rerun, the published version it builds on (`v{prior_stack_version}`, with its `{prior_libraries}` count); and the resolved input mode (auto-detect, explicit dependency list, or compose mode), with the folder code mode scans (`{scan_root}`).

### 5. Save the Run's Bindings

Save the bindings above in `{runFile}`, so a step that lost one to compaction reads it back. Resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}`; first existing path wins. If neither exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `init:run-state`) with "**Cannot proceed.** `skf-atomic-write.py` is missing, so the run's bindings cannot be saved. Re-install SKF, then re-run." Otherwise stage `{run_dir}/run-bindings.json` with a file write: one JSON object keyed by each binding's own name, an input not given being `null`:

```json
{"stack_name": "<stack name>", "headless_mode": false, "project_root": "<path>", "scan_root": "<path>",
 "compose_mode": false, "architecture_doc_path": null, "explicit_deps": null, "scope_overrides": null,
 "prior_active_version": null, "prior_stack_version": null, "prior_libraries": null,
 "stackSkillTemplatePath": "<path>", "integrationPatternsPath": "<path>", "onCompleteCommand": "",
 "forge_tier": "<tier>", "detected_tier": "<tier>", "available_tools": ["<tool>"]}
```

`forge_tier` is the run tier, after §1's override and §2's downgrade; `detected_tier` is the one `forge-tier.yaml` names; the three `prior_` keys are §0's, `null` on a new stack, with `prior_libraries` the published `libraries` list. Then run:

```bash
uv run {atomicWriteHelper} write --target "{runFile}" < "{run_dir}/run-bindings.json"
```

If it exits non-zero, HALT (exit 4, `halt_reason: "write-failure"`, phase `init:run-state`) with "**Cannot proceed.** The run's bindings could not be saved to `{runFile}`: {the first stderr line}."

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{composeNextStepFile}` when `compose_mode` is true, else `{nextStepFile}`.


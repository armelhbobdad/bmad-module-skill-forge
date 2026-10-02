---
nextStepFile: 'detect-manifests.md'
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
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize

## STEP GOAL:

Load forge tier configuration, validate prerequisites, bind and check the invocation inputs, and choose the mode and the folder code mode scans.

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

**Halt envelope.** Every later HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}"}`, leaving out `skill_name` before §0 binds `{stack_name}` and adding `"path"` when the halt names a file, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

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

**Required for all tiers:**
- File I/O capability (read project files)

**Tier-dependent tools:**
- **Quick:** gh_bridge (source reading) — graceful degradation to local file reading if unavailable
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

   **Headless default (B8):** do NOT prompt: accept the suggestion (`compose_mode: true`, `architecture_doc_path: null`). With no manifests, code mode would only halt at step 2 (`no-manifests`) or rank `explicit_deps` in a tree that declares none of them, while `kept[]` holds SKF skills (those `explicit_deps` names, when given): compose is the path that produces the stack. Record the auto-decision: stage `{"gate": "init.compose-suggestion", "default_action": "accept", "taken_action": "accept", "reason": "headless: no manifests and {N} SKF skills, so compose mode", "evidence": {"discoverable_skills": {N}}}` as `{run_dir}/decision.json` and run:

   ```bash
   uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
   ```

**Scan scope (code mode).** Run the scan call above (resolving `{scanManifestsHelper}` as rule 4 does) when rule 2 set the mode, so `{manifest_scan}` holds the scan of `{scan_root}`. When its `folders[]` lists more than one folder and no `project_path` was given, ask once which folder the stack covers:

"**This project holds several packages.** Type **A** to build the stack for the whole project (the default), or the folder of one package: {each `folders[]` entry's `path`, with its `names`}."

A folder answer resolves from `project_root`. When it is no folder, ask again; otherwise set `{scan_root}` to it and run the scan call again, replacing `{manifest_scan}`. **Headless:** do not ask; keep the project root, record the auto-decision as B8 does, with `{"gate": "init.scan-root", "default_action": "A", "taken_action": "A", "reason": "headless: manifests in {N} folders, so the whole project; pass project_path to scan one package", "evidence": {"folders": {N}}}`, `{N}` being the `folders[]` count: its `reason` tells the user to pass `project_path`.

Skills use version-nested directories: see `knowledge/version-paths.md` for the path templates.

If compose_mode:
- Display: "**Compose mode detected.** Synthesizing stack skill from existing skills + architecture document."

### 4. Display Initialization Summary

Report that the Stack Skill Forge is initialized, naming: the project (`{project_name}`); the forge tier (`{forge_tier}`) with its positive-capability framing (Quick = source reading and import counting; Forge = AST-backed structural analysis; Forge+ = AST structural + CCC semantic search for the files that show each integration; Deep = full intelligence: structural + contextual + temporal); the available tools (`{tool_list}`); the stack name (`{stack_name}`); and the resolved input mode (auto-detect, explicit dependency list, or compose mode), with the folder code mode scans (`{scan_root}`).

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


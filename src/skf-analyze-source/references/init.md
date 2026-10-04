---
nextStepFile: 'scan-project.md'
continueFile: 'continue.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
templateFile: '{analysisReportTemplatePath}'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Analysis

## STEP GOAL:

To initialize the analyze-source workflow by loading configuration, detecting continuation state, taking the target project path, the analysis goal and the scope from the invocation or one opening question, checking for existing skills, and creating the analysis report document.

## Rules

- Focus only on initialization: do not begin scanning or analysis
- Use what the invocation already says before asking anything, and ask at most one opening question
- Verify prerequisites before proceeding

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "<auto when the invocation carries [auto], else interactive>"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Check for Existing Report (Continuation Detection)

Look for {outputFile}.

**IF the file exists AND has `stepsCompleted` with entries:** the report filename is keyed to `{project_name}` (the forge workspace), not the analyzed target, so the report may belong to another analysis or to one that already ended. Apply the first rule that holds:

1. **Finished:** `stepsCompleted` holds `generate-briefs` or `auto-scope`: that analysis already ended (with its briefs, or with none). Archive it (below), announce "**The previous analysis of this workspace is finished: archived as <name>; starting a fresh analysis.**", and continue to section 2. A finished report is never resumed, in headless mode either.
2. **Auto invocation or auto report:** this invocation carries the `[auto]` flag (e.g. `AN[auto]`), or the report's `mode` is `'auto'` (an `[auto]` run that was interrupted or ended at step 1a's coexistence gate with [M]erge or [S]kip). Auto mode is one pass that never resumes, so archive the unfinished report the same way, announce "**An `[auto]` analysis never resumes: archived the unfinished report as <name>; starting a fresh analysis.**", and continue to section 2.
3. **Unfinished:** establish the requested target and compare it to the report's. Take `project_paths[]` from the invocation as section 3 says (`--project-path`, comma-split, or a path the message names); when it gives none, ask section 3's opening question now (a headless run halts there instead), once: section 3 then asks nothing more. Read the report's frontmatter `project_paths`.
   - **Same target:** compare the ref and hint flags this invocation passes with the report's frontmatter: `--target-ref` or `--target-refs`, resolved to each project path's ref as section 4 does, against `refs`, and `--scope-hint` and `--intent-hint` against `scope_hint` and `intent_hint`. A flag the invocation does not pass changes nothing.
     - **The inputs match:** "**Found an unfinished analysis report. Resuming the previous session...**" Load, read entirely, then execute {continueFile}. **STOP HERE**: do not continue this sequence. Headless runs resume it too.
     - **An input differs:** the later steps would read the report's old values, so archive it and announce "**The inputs changed: archived as <name>; starting a fresh analysis.**" In headless mode, also run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'inputs changed: the unfinished report was archived as <name>'`, a single quote in it written as a backtick (if it fails, go on). Then continue to section 2: section 3 keeps the path already set, and section 4 resolves the refs again.
   - **Different target (stale collision):** archive it, announce "**Existing report belongs to a different target: archived as <name>; starting a fresh analysis.**", then continue to section 2 (section 3 keeps the path already set).

**To archive a report** (rules 1 and 2, changed inputs and a different target; a report that resumes stays where it is), rename it, never overwrite it:

```bash
archive="{forge_data_folder}/analyze-source-report-{project_name}-$(date -u +%Y%m%d-%H%M%S).md" && mv -n "{outputFile}" "$archive" && printf '%s\n' "$archive"
```

and use the path it prints as `<name>`. If the rename fails, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `init:1`, path `{outputFile}`): "The earlier analysis report could not be archived: {the first stderr line}."

**IF the file does not exist OR stepsCompleted is empty:**
- Continue to section 2

### 2. Verify Prerequisites

**Check forge-tier.yaml:**
- Look for `{sidecar_path}/forge-tier.yaml`
- **IF missing:** HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `init:2`, path `{sidecar_path}/forge-tier.yaml`): "**Cannot proceed.** forge-tier.yaml not found at `{sidecar_path}/forge-tier.yaml`. Please run the setup workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."
- **IF found:** Read and note the forge tier value

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

"**Forge tier detected:** {tier} — analysis depth will be calibrated accordingly."

### 2b. Auto Mode Check

**Check for `[auto]` flag:** If `[auto]` was passed as a bracket modifier in the pipeline context (e.g., `AN[auto]`), set `{auto_mode}` = true.

**IF `{auto_mode}` is true:**

1. **Resolve project path:** If `project_paths[]` is already populated (from §1 continuation detection or `--project-path` arg), use it. Otherwise, if `--project-path <path>` was passed at invocation, set `project_paths[]` from it (comma-split if multiple). If neither is available, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:2b`): "**Auto mode requires `--project-path`: no project path available.**"
2. **Validate the path(s):** For each provided path/URL, check that it exists (local) or is accessible (remote). If any invalid: HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `init:2b`, path `{path}`): "**Path `{path}` doesn't appear to be valid.**"
3. **Take the hints:** `intent_hint` ← the `--intent-hint` value and `scope_hint` ← the `--scope-hint` value (empty when the flag is absent). Step 1a reads both, and so does the interactive chain it may fall back to.
4. **Create the analysis report** from {templateFile}. First build `existing_skills` and `existing_briefs` as section 5 does, without its messages: the step-by-step analysis an unclassified repository falls back to reads them. Populate frontmatter:
   ```yaml
   stepsCompleted: ['init']
   lastStep: 'init'
   lastContinued: ''
   date: '{current_date}'
   user_name: '{user_name}'
   project_name: '{project_name}'
   project_paths: ['{provided_project_path}']
   forge_tier: '{detected_tier}'
   existing_skills: [{list of existing skill names}]
   existing_briefs: [{name and path of each existing brief, as {name: '...', path: '...'}}]
   intent_hint: '{intent_hint}'
   scope_hint: '{scope_hint}'
   confirmed_units: []
   stack_skill_candidates: []
   nextWorkflow: ''
   mode: 'auto'
   ```
5. "**Auto mode activated: bypassing interactive analysis.**"
6. **Route to auto-scope:** Load, read fully, then execute `references/step-auto-scope.md`. **STOP HERE**: do not continue to §3 or any subsequent section.

**IF `{auto_mode}` is not true:** continue to §3.

### 3. Opening Question

Read the invocation first: its flags (`--project-path`, comma-split for several paths; `--intent-hint`; `--scope-hint`) and, in an interactive run, its message, which may name a path or URL, the goal of the analysis, or folders and packages to focus on or skip ("analyze /work/mono, I only care about auth, skip vendor/"). A flag wins over the message. `project_paths[]` set by section 1 stays as it is.

- `intent_hint`: the goal, in the user's words (a domain such as authentication, the consumers the skills serve, a constraint such as stable public APIs only).
- `scope_hint`: the folders or packages to focus on, and those to skip.

**Headless** (`{headless_mode}` true): ask nothing. With no path from a flag or section 1, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:3`): "**No project path: headless mode requires `--project-path`.**" A hint no flag gave is empty: a headless run never reads one from the message.

**Interactive:** ask at most one question, and only for what is still missing:

- **No path yet:** "**Which project should I analyze?** Give the root path(s) or URL(s), comma-separated for several repositories (`/path/to/project`, `owner/repo, owner/repo2`). Optionally add what you want out of it and anything to focus on or skip (for example: auth packages only, skip `vendor/`)."
- **A path, but no goal:** "**What should this analysis focus on, or keep out?** A domain, packages, folders to skip. Press Enter to analyze everything."
- **A path and a goal:** ask nothing.

Wait for the answer, then fill what is still missing from it: `project_paths[]`, `intent_hint` and `scope_hint`, each empty when the answer gives none. A value the invocation gave stays.

### 4. Validate the Inputs

**Paths:** for each entry of `project_paths[]`, check that it exists (local) or is accessible (remote). An invalid one: "Path `{path}` doesn't appear to be valid. Please correct it." and wait for the corrected path. In headless mode no one can correct it: HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `init:4`, path `{path}`) with that message.

**Ref pins:** `--target-ref <ref>` names one git tag or branch for every project path: `target_ref` ← it. `--target-refs <mapping>` names one per path, as comma-separated `path:ref` pairs (`owner/repo:v1.0.0,owner/repo2:main`), and every key must be an entry of `project_paths[]`, else HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:4`): "`--target-refs` key `{key}` does not match any entry in project_paths." The two are mutually exclusive: when both are passed, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:4`): "`--target-refs` and `--target-ref` are mutually exclusive. Use `--target-refs` for one ref per path, or `--target-ref` for one ref for every path." Resolve each project path's **ref** once, here: its `--target-refs` entry, else `target_ref`, else none (the default ref: HEAD for a local path, the default branch for a remote one). `refs` ← each project path that has a ref, mapped to it (`{}` when none has one). Every later step reads a path's ref from `refs` alone: scan-project reads each path at its ref, and generate-briefs writes each unit's ref into its brief as `target_ref`.

### 5. Check for Existing Skills

A unit is already skilled when a compiled skill carries its name. A brief alone does not make it one: an earlier analysis, archived in section 1, may have written it. **Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If neither exists, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `init:5`): "`skf-skill-inventory.py` is missing. Re-install SKF." List the compiled skills:

```bash
uv run {skillInventoryHelper} "{skills_output_folder}"
```

`existing_skills` ← the `name` of every `skills[]` entry whose `skf_skill` is true (none when it exits non-zero: no skills folder yet). A skill SKF did not generate is left out: update-skill, which an already-skilled unit is sent to, changes only the skills SKF generated. Then scan `{forge_data_folder}/*/skill-brief.yaml` (one level deep: each skill has its own subdirectory): `existing_briefs` ← `{name, path}` of each brief whose folder name is not in `existing_skills`.

**IF existing skills found:**
"**Existing skills detected:**
{list each existing skill name and path}

These units will be flagged as 'already skilled' during analysis. If source changes are detected, I'll recommend running update-skill instead of generating new briefs."

**IF existing briefs found:**
"**Briefs with no compiled skill yet:** {list each name and path}. Their units are analyzed again; a brief is rewritten only when you confirm its unit."

**IF neither found:**
"**No existing skills found.** All identified units will be treated as new."

### 6. Create Analysis Report

Create {outputFile} from {templateFile}. If the write fails, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `init:6`, path `{outputFile}`): "The analysis report could not be written: {the error}."

**Populate frontmatter:**
```yaml
stepsCompleted: ['init']
lastStep: 'init'
lastContinued: ''
date: '{current_date}'
user_name: '{user_name}'
project_name: '{project_name}'
project_paths: ['{provided_project_path}']
target_ref: '{target_ref, or empty}'
refs: {each project path with a ref: its ref}
forge_tier: '{detected_tier}'
existing_skills: [{list of existing skill names}]
existing_briefs: [{name and path of each existing brief, as {name: '...', path: '...'}}]
intent_hint: '{intent_hint or empty string}'
scope_hint: '{scope_hint or empty string}'
confirmed_units: []
stack_skill_candidates: []
nextWorkflow: ''
```

`target_ref` stays for a path that discover-additional-source adds later, which takes it as its ref.

"**Initialization complete.**

**Project:** {project_paths, each with its ref when it has one}
**Forge Tier:** {forge_tier}
**Existing Skills:** {count}
**Goal:** {intent_hint, or 'None: every unit is analyzed'}
**Scope Hints:** {scope_hint, or 'None: full project analysis'}

**Proceeding to project scan...**"

### 7. Proceed to Next Step

Initialization is complete and the report is created — immediately load, read the entire file, then execute {nextStepFile}. This step has no user choices.


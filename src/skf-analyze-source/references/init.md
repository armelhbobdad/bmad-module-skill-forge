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

To initialize the analyze-source workflow by loading configuration, detecting continuation state, accepting the target project path, checking for existing skills, and creating the analysis report document.

## Rules

- Focus only on initialization — do not begin scanning or analysis
- Collect project path and scope hints from user
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
2. **Auto invocation:** this invocation carries the `[auto]` flag (e.g. `AN[auto]`). Auto mode is one pass that never resumes, so archive the unfinished report the same way, announce it, and continue to section 2.
3. **Unfinished:** establish the requested target and compare it to the report's. If `--project-path <path>` was passed at invocation, set `project_paths[]` from it (comma-split if multiple); otherwise collect the path(s) with the section-3 "Collect Project Path" prompt (a headless run without `--project-path` halts there) and store them as `project_paths[]`. Section 3 does not re-prompt when `project_paths[]` is already populated here. Read the report's frontmatter `project_paths`.
   - **Same target:** "**Found an unfinished analysis report. Resuming the previous session...**" Load, read entirely, then execute {continueFile}. **STOP HERE**: do not continue this sequence. Headless runs resume it too. ({continueFile} is mode-aware: a report written by an interrupted auto run resumes through the auto path, not the interactive chain.)
   - **Different target (stale collision):** archive it, announce "**Existing report belongs to a different target: archived as <name>; starting a fresh analysis.**", then continue to section 2 (section 3 keeps the path already set).

**To archive a report** (rules 1 and 2 and a different target; a report that resumes stays where it is), rename it, never overwrite it:

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
3. **Create the analysis report** from {templateFile}. Populate frontmatter:
   ```yaml
   stepsCompleted: ['init']
   lastStep: 'init'
   lastContinued: ''
   date: '{current_date}'
   user_name: '{user_name}'
   project_name: '{project_name}'
   project_paths: ['{provided_project_path}']
   forge_tier: '{detected_tier}'
   existing_skills: []
   confirmed_units: []
   stack_skill_candidates: []
   nextWorkflow: ''
   mode: 'auto'
   ```
4. "**Auto mode activated — bypassing interactive analysis.**"
5. **Route to auto-scope:** Load, read fully, then execute `references/step-auto-scope.md`. **STOP HERE** — do not continue to §3 or any subsequent section.

**IF `{auto_mode}` is not true:**
Continue to §3 as normal — the entire interactive flow below is unchanged.

### 3. Collect Project Path

**Headless flag consumption:** If `project_paths[]` is already populated (e.g. collected by the section-1 stale-collision guard) OR `--project-path <path>` was passed at invocation, set/keep `project_paths[]` (comma-split the flag value if multiple paths were supplied), skip the prompt below, and proceed to validation. If `{headless_mode}` is true and no path is available from either source, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:3`): "**No project path: headless mode requires `--project-path`.**" (interactive prompting is unavailable headless). Otherwise prompt as today.

**Per-path ref overrides (`--target-refs`):** If `--target-refs <mapping>` was passed at invocation, parse it as a comma-separated list of `path:ref` pairs (e.g., `owner/repo:v1.0.0,owner/repo2:main`). Build a `constituent_refs` map from the pairs. Each key must match an entry in `project_paths[]` (validated after path collection). When `--target-refs` is absent but multiple `project_paths` exist, set `constituent_refs` to `{}` (empty: all paths use default ref resolution). When only a single path exists, omit `constituent_refs` entirely (use `target_ref` if set on the brief). `constituent_refs` and `target_ref` are mutually exclusive: if both are supplied, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:3`): "`--target-refs` and `--target-ref` are mutually exclusive. Use `--target-refs` for multi-path analysis, or `--target-ref` for single-path."

"**Please provide the project root path(s) to analyze** — I'll identify discrete skillable units and produce a skill-brief.yaml for each.

This can be:
- A single root directory of a repo or multi-service project
- Multiple paths or URLs (comma-separated) for multi-repo analysis (e.g., integration/stack skills)

Examples:
- `/path/to/project`
- `owner/repo, owner/repo2`
- `/path/to/project, https://github.com/owner/repo2`"

Wait for user input.

**Validate the path(s):**
- For each provided path/URL: check that it exists (local) or is accessible (remote)
- **IF any invalid:** "Path `{path}` doesn't appear to be valid. Please correct it." In headless mode no one can correct it: HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `init:3`, path `{path}`) with that message.
- Store as `project_paths[]` array in report frontmatter (single path stored as 1-element array for consistency)
- **IF `constituent_refs` was built from `--target-refs`:** Validate that every key in the map matches an entry in `project_paths[]`. If any key has no matching path, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:3`): "constituent_refs key `{key}` does not match any entry in project_paths."

**Collect intent hint** (drives recommendation ranking in Step 5):

**Headless flag consumption:** If `--intent-hint <text>` was passed at invocation, set workflow-context `intent_hint` directly from the flag value, skip the prompt below, and proceed. If `{headless_mode}` is true and no `--intent-hint` was supplied, set `intent_hint = ""` (empty) and proceed without prompting.

"**Optional: What are you hoping to get out of this analysis?**

For example:
- Skills for a specific domain (e.g., 'authentication and authorization')
- Target consumer agents (e.g., 'skills our backend team's AI assistants will call')
- Constraints (e.g., 'we only want stable public APIs, no internal modules')

Type details, or press Enter to skip."

Wait for user input. Store as workflow-context `intent_hint` (empty string if skipped).

### 4. Collect Optional Scope Hints

**Headless flag consumption:** If `--scope-hint <text>` was passed at invocation, set workflow-context `scope_hint` directly from the flag value, skip the prompt below, and proceed. If `{headless_mode}` is true and no `--scope-hint` was supplied, set `scope_hint = ""` (empty) and proceed without prompting.

"**Optional: Do you have scope hints to narrow the analysis?**

For example:
- Specific packages to focus on (e.g., `packages/auth`, `services/api`)
- Directories to exclude (e.g., `vendor/`, `node_modules/`, `dist/`)

Enter scope hints, or press Enter to analyze the entire project."

Wait for user input. Document any hints provided.

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
constituent_refs: {map from --target-refs, or omit if single path}
forge_tier: '{detected_tier}'
existing_skills: [{list of existing skill names}]
existing_briefs: [{name and path of each existing brief, as {name: '...', path: '...'}}]
intent_hint: '{intent_hint or empty string}'
scope_hint: '{scope_hint or empty string}'
confirmed_units: []
stack_skill_candidates: []
nextWorkflow: ''
```

**`constituent_refs` presence rules:** Include the field only when `project_paths` has more than one entry. When present, keys are path strings matching `project_paths[]` entries, values are explicit git refs (tag/branch/commit). Paths with no explicit ref have no entry in the map (default ref resolution applies). Downstream steps (scan-project, brief generation) read this map to resolve per-constituent refs when cloning or reading off-HEAD constituents.

"**Initialization complete.**

**Project:** {project_path}
**Forge Tier:** {forge_tier}
**Existing Skills:** {count}
**Scope Hints:** {hints or 'None — full project analysis'}

**Proceeding to project scan...**"

### 7. Proceed to Next Step

Initialization is complete and the report is created — immediately load, read the entire file, then execute {nextStepFile}. This step has no user choices.


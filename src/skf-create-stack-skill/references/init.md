---
nextStepFile: 'detect-manifests.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize

## STEP GOAL:

Load forge tier configuration, validate prerequisites, and prepare the stack skill workflow for execution.

## Rules

- Focus only on loading configuration and validating prerequisites — do not start analyzing dependencies

## MANDATORY SEQUENCE

### 0. Validate Project Config

Before anything else, load `{project-root}/_bmad/skf/config.yaml`. If the file is missing OR fails YAML parse OR lacks the required top-level keys (`project_name`, `output_folder`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`), HALT with:

"**Cannot proceed.** SKF is not initialized for this project (config.yaml missing or malformed).

**Required:** Run `skf init` first.

**Halting workflow.**"

Then emit the result envelope on stderr per the Result Contract in SKILL.md (`project_name` is unresolved here, so `skill_name` is `null`), and STOP — do not proceed:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":null,"stack_libraries":[],"mode":null,"exit_code":2,"halt_reason":"config-missing"}
```

### 1. Load Forge Tier Configuration

Load `{forgeTierFile}` from the Ferris sidecar.

**If forge-tier.yaml does not exist:**

"**Cannot proceed.** The setup workflow has not been run for this project.

**Required:** Run `setup` first to detect available tools and determine your forge tier.

**Halting workflow.**"

Then emit the result envelope on stderr per the Result Contract in SKILL.md (config loaded, so `skill_name` is known; `mode` is not yet resolved), and STOP — do not proceed:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":null,"exit_code":3,"halt_reason":"forge-tier-missing"}
```

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
- **Forge+:** ast_bridge + ccc_bridge (ccc semantic co-import augmentation) — ccc available for step 5
- **Deep:** qmd_bridge (QMD temporal enrichment) — required for Deep tier

See `knowledge/tool-resolution.md` for how each bridge name resolves to concrete tools per IDE environment.

Report tool availability. If a tier-required tool is missing, downgrade tier and note:

"**Tier adjusted:** {original_tier} → {adjusted_tier} — {missing_tool} unavailable."

### 3. Accept Optional Inputs

Check if the user provided:

**Explicit dependency list:**
- If provided, store as `explicit_deps` and skip auto-detection in step 02
- Format: comma-separated library names or a file path

**Scope overrides:**
- If provided, store as `scope_overrides` for use in step 03
- Format: `library_name: include|exclude`

**Compose mode detection:**

Set `compose_mode: false` as the default.

Skills use version-nested directories — see `knowledge/version-paths.md` for the full path templates and resolution rules.

- If user provides an architecture document path for composition or explicitly requests compose mode → set `compose_mode: true` and store `architecture_doc_path`
- If no manifest files exist in project root AND at least one skill is discoverable in `{skills_output_folder}` → suggest compose mode to the user and ask for optional architecture document path
  - **Skill discovery (version-aware):** First, read `{skills_output_folder}/.export-manifest.json` — each entry in `exports` names a skill with an `active_version`, which resolves to `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/` containing `SKILL.md` and `metadata.json`. If the export manifest does not exist or is empty, fall back to scanning for `active` symlinks: check `{skills_output_folder}/*/active/*/SKILL.md` — each match indicates a skill whose package lives at `{skills_output_folder}/{skill-name}/active/{skill-name}/` (the `{active_skill}` template).
  - **Headless default (B8):** If `{headless_mode}` is true, do NOT prompt — auto-accept the suggestion: set `compose_mode: true` and `architecture_doc_path: null` (unless an architecture doc path was supplied via the optional inputs above). This is the constructive default: with no manifests present, code-mode would only halt at step 2 (`no-manifests`), so compose is the sole path that produces output. Log the auto-decision by appending to `workflow_warnings[]`: `{step: "step-01", severity: "info", code: "headless-compose-autodetect", message: "no manifests + {N} discoverable skills — auto-selected compose mode", context: {discoverable_skills: {N}}}`.
  - If user accepts → set `compose_mode: true` and store `architecture_doc_path` (may be `null` if user chose not to provide one)
  - If user declines → `compose_mode` remains `false`, continue with code-mode

If compose_mode:
- Display: "**Compose mode detected.** Synthesizing stack skill from existing skills + architecture document."

If no optional inputs provided, auto-detection will be used.

### 4. Display Initialization Summary

Report that the Stack Skill Forge is initialized, naming: the project (`{project_name}`); the forge tier (`{forge_tier}`) with its positive-capability framing (Quick = source reading and import counting; Forge = AST-backed structural analysis; Forge+ = AST structural + CCC semantic co-import augmentation; Deep = full intelligence — structural + contextual + temporal); the available tools (`{tool_list}`); and the resolved input mode (auto-detect, explicit dependency list, or compose mode).

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


---
nextStepFile: './step-02-detect-manifests.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

# Step 1: Initialize

## STEP GOAL:

Load forge tier configuration, validate prerequisites, and prepare the stack skill workflow for execution.

## Rules

- Focus only on loading configuration and validating prerequisites — do not start analyzing dependencies

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Forge Tier Configuration

Load `{forgeTierFile}` from the Ferris sidecar.

**If forge-tier.yaml does not exist:**

"**Cannot proceed.** The setup workflow has not been run for this project.

**Required:** Run `setup` first to detect available tools and determine your forge tier.

**Halting workflow.**"

STOP — do not proceed.

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
- **Forge+:** ast_bridge + ccc_bridge (ccc semantic co-import augmentation) — ccc available for step-05
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
  - If user accepts → set `compose_mode: true` and store `architecture_doc_path` (may be `null` if user chose not to provide one)
  - If user declines → `compose_mode` remains `false`, continue with code-mode

If compose_mode:
- Display: "**Compose mode detected.** Synthesizing stack skill from existing skills + architecture document."

If no optional inputs provided, auto-detection will be used.

### 4. Display Initialization Summary

"**Stack Skill Forge initialized.**

**Project:** {project_name}
**Forge Tier:** {forge_tier} — {tier_description}

Where tier_description follows positive capability framing:
- Quick: "Source reading and import counting"
- Forge: "AST-backed structural analysis"
- Forge+: "AST structural + CCC semantic co-import augmentation"
- Deep: "Full intelligence — structural + contextual + temporal"

**Available Tools:** {tool_list}
**Input Mode:** {auto-detect | explicit dependency list | compose mode}

**If compose mode:** Proceeding to skill loading...
**If code mode:** Proceeding to manifest detection..."

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


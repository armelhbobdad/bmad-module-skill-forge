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

STOP — do not proceed.

### 0b. Resume Check

Before any further init work, check for an interrupted prior run.

**Probe path.** Resolve `{resume_skill_name}` as `{project_name}-stack` (the same skill name used at step 7) and probe `{forge_data_folder}/{resume_skill_name}/in-progress.json`. (The file lives at the version-agnostic skill root so it can be found before `{version}` resolution.)

**If no in-progress.json exists:** Continue to §1.

**If in-progress.json exists:** Load and parse it. Read `last_completed_step` and `started_at` (ISO-8601 timestamp). Surface a soft gate:

"**Resume previous run?**

Found a previous in-progress run at `{forge_data_folder}/{resume_skill_name}/in-progress.json` from {started_at}, last completed at step {last_completed_step}.

- **[C] Continue** (recommended) — resume from the next step after {last_completed_step}, restoring saved workflow state.
- **[F] Fresh** — archive the existing in-progress.json (rename to `in-progress.{timestamp}.json`) and start over from step 1.
- **[X] Cancel and exit** — leave the in-progress.json untouched and halt.

Select [C/F/X]:"

**Headless default:** `[C]` Continue.

**On [C] Continue:**
1. Restore workflow context from in-progress.json fields: `last_completed_step`, `workflow_state` (mode, tier, scope), and any accumulator fields (partial extractions, ranked libraries, integration pairs, compile-stack output) that the writing step persisted.
2. Determine the resume target: the step file that runs immediately after `last_completed_step`.
3. Jump directly to that step file by loading and executing it (skip the remaining §0b–§5 init substeps for this run).

**On [F] Fresh:**
1. Compute `{archive_timestamp}` as the current UTC time in `YYYYMMDDTHHMMSSZ` form.
2. Rename `{forge_data_folder}/{resume_skill_name}/in-progress.json` → `{forge_data_folder}/{resume_skill_name}/in-progress.{archive_timestamp}.json`.
3. Continue with §1 of this file as if no prior run existed.

**On [X] Cancel and exit:** HARD HALT with exit code 6 (user-cancelled). Do NOT modify the in-progress.json. Emit the result envelope on stderr per the Result Contract in SKILL.md:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{resume_skill_name}","stack_libraries":[],"mode":null,"exit_code":6,"halt_reason":"user-cancelled"}
```

**in-progress.json schema (read side).** This PR wires only the READ side of the resume protocol. The WRITE side — each stage step persisting an updated in-progress.json after it completes — is deferred to a follow-up PR. When write-side wiring lands, each step writes the file via `skf-atomic-write.py write` at the end of its mandatory sequence with this shape:

```json
{
  "schema_version": "1.0",
  "skill_name": "{project_name}-stack",
  "started_at": "{ISO-8601 of step 1 start}",
  "updated_at": "{ISO-8601 of most recent step completion}",
  "last_completed_step": "step-NN",
  "workflow_state": {
    "mode": "code|compose",
    "forge_tier": "Quick|Forge|Forge+|Deep",
    "headless_mode": false,
    "scope": {"explicit_deps": [], "scope_overrides": {}, "architecture_doc_path": null}
  },
  "accumulators": {
    "manifests": [],
    "ranked_libraries": [],
    "extractions": {},
    "integration_pairs": [],
    "compiled_stack": null,
    "workflow_warnings": []
  }
}
```

Until the write side is wired, in-progress.json will not naturally appear and §0b will fall through to §1 on every run. The resume gate is a no-op until that follow-up lands.

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


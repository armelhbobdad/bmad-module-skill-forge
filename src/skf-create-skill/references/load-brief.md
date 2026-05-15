---
nextStepFile: 'ecosystem-check.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
preferencesFile: '{sidecar_path}/preferences.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Load Brief

## STEP GOAL:

To load and validate the skill-brief.yaml compilation config, resolve the source code location, and load the forge tier from sidecar to determine available capabilities for the compilation pipeline.

## Rules

- Focus only on loading brief, resolving source, and determining tier — do not begin extraction or compilation
- Do not write any output files — this step only loads and validates

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Forge Tier

Load `{forgeTierFile}` completely.

**If file does not exist:**
Halt with: "Forge halted: No forge configuration found. Run [SF] Setup Forge first to detect tools and set your tier."

**If file exists:**
Extract and report:
- `tier`: Quick, Forge, Forge+, or Deep
- `tools`: which tools are available (gh, ast-grep, ccc, qmd)
- `ccc_index`: ccc index state (status, indexed_path, last_indexed) — needed by step 2b

**Apply tier override:** Read `{preferencesFile}`. If `tier_override` is set and is one of the exact valid tier values (`Quick`, `Forge`, `Forge+`, `Deep`), use it instead of the detected tier. **If `tier_override` is set but is NOT one of those four values:** log a warning — "Unknown tier_override `{value}` in preferences.yaml; falling back to detected tier `{detected_tier}`. Valid values: Quick, Forge, Forge+, Deep." — and use the detected tier. Never silently apply an unknown override value, and never map it heuristically to a tier.

**Record the decision:** append an entry to the in-context `headless_decisions[]` buffer (initialize to `[]` at the start of this step if absent) whenever a non-interactive choice is made automatically — both the valid-override path AND the rejected-override path:

- Valid override applied: `{step: "load-brief", gate: "tier-override", decision: "apply", value: "{tier_override}", rationale: "explicit preferences.yaml tier_override", timestamp: {ISO}}`
- Invalid override rejected: `{step: "load-brief", gate: "tier-override", decision: "reject-invalid", value: "{tier_override}", fallback: "{detected_tier}", rationale: "tier_override not in {Quick,Forge,Forge+,Deep}", timestamp: {ISO}}`

Step-05 §7 reads `headless_decisions[]` and emits an "Auto-Decisions" section into `evidence-report.md` so reviewers can audit every silent choice the workflow made.

### 2. Discover Skill Brief

**If user provided a specific brief path or skill name:**
- If the value looks like a file path (starts with `/`, `./`, `~`, or contains path separators): treat it as a direct file path and load it
- Otherwise, treat it as a skill name and search `{forge_data_folder}/{skill-name}/skill-brief.yaml`
- If found, load it completely

**If user invoked with --batch flag:**
- Check `{sidecar_path}/batch-state.yaml` for an active batch checkpoint:
  - If `batch_active: true`: validate the checkpoint before trusting it. Both conditions below MUST hold:
    1. `0 <= current_index < len(brief_list)` — the index points inside the recorded list.
    2. `os.path.exists(brief_list[current_index])` — the brief file is still on disk.
    If both hold, load the brief at `brief_list[current_index]` (resuming a batch loop from step 8). If **either** check fails, the checkpoint is stale (briefs renamed, moved, or deleted between runs; index off the end after a partial failure). Log a warning — "Stale batch checkpoint — current_index={i}, brief_list length={n}, brief_exists={bool}. Resetting and re-discovering." — then set `batch_active: false` in `batch-state.yaml` and fall through to the no-checkpoint branch below.
  - If no checkpoint exists or `batch_active` is false: search specified directory for all `skill-brief.yaml` files, list discovered briefs with skill names, store list for batch loop processing, and load the FIRST brief

**If no brief found:**
Halt with: "No skill brief found. Run [BS] Brief Skill to create one, or use [QS] Quick Skill for brief-less generation."

### 3. Validate Brief Structure

Check that the loaded skill-brief.yaml contains required fields:

**Required fields:**
- `name` — skill identifier (kebab-case)
- `version` — source version to compile against
- `source_repo` — GitHub owner/repo or local path (**optional when `source_type: "docs-only"`**)
- `language` — primary source language
- `scope` — what to extract. Accepts either a string (simple scope description, e.g., "all public exports") or an object with sub-fields: `type` (e.g., `"component-library"`), `include`, `exclude`, `notes`, and optionally `demo_patterns`, `registry_path`, `ui_variants` for component libraries

**Optional fields:**
- `source_type` — `"source"` (default) or `"docs-only"` (external documentation only)
- `doc_urls` — array of `{url, label}` documentation URLs (required when `source_type: "docs-only"`)
- `source_branch` — branch to use (default: main/master)
- `source_authority` — official/community/internal (default: community; forced to `community` for docs-only)
- `target_version` — specific version to compile against (triggers **explicit** tag resolution for remote repos; see source-resolution-protocols.md). When absent, the workflow falls back to **implicit** tag resolution from `brief.version` for remote sources — see below.
- `include_patterns` — file glob patterns to include
- `exclude_patterns` — file glob patterns to exclude
- `description` — human description of the skill
- `scripts_intent` — `"none"` to skip scripts detection, omit for default auto-detection
- `assets_intent` — `"none"` to skip assets detection, omit for default auto-detection

**Docs-only validation:** When `source_type: "docs-only"`, `source_repo` is not required but `doc_urls` must have at least one entry. `source_authority` is forced to `community`.

**If required fields missing:**
Halt with specific error: "Brief validation failed: missing required field `{field}`. Update your skill-brief.yaml and re-run."

**Name format check (run after required-field check, before any path creation):** validate `brief.name` against the regex `^[a-z0-9][a-z0-9-]{0,63}$` — 1-64 characters, lowercase alphanumeric plus hyphens, must start with a letter or digit, no leading hyphen, no uppercase, no underscores, no slashes. This matches the agentskills.io skill-name rule and the directory-name constraint that `skill-check`'s `frontmatter.name_matches_directory` rule will later enforce. If validation fails, halt BEFORE any directory is created or any path is resolved: "Brief validation failed: `name` field `{value}` does not match required pattern `^[a-z0-9][a-z0-9-]{0,63}$`. Skill names must be 1-64 chars, lowercase alphanumeric plus hyphens, no leading hyphen, no underscores, no slashes. Update your skill-brief.yaml and re-run."

**Version non-empty check:** reject `brief.version` if absent, empty, or whitespace-only (`version.strip() == ""`). Halt: "Brief validation failed: `version` field is required and must be non-empty. Update your skill-brief.yaml and re-run." This guards downstream directory resolution — an empty version would later create paths like `{skills_output_folder}/{name}//` with a stray double-slash, which is a nightmare to clean up.

### 4. Resolve Source Code Location

**If `source_type: "docs-only"`:** Skip source resolution. Set `source_root: null` in context. Proceed directly to section 5 (Report Initialization) — docs-only skills have no source to resolve.

**If source_repo is a GitHub URL or owner/repo format:**
- Verify repository exists via `gh_bridge.list_tree(owner, repo, branch)` — **Tool resolution:** `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1` or direct file listing if local; see `knowledge/tool-resolution.md`
- If branch not specified, detect default branch
- Store resolved: owner, repo, branch, file tree — note: `source_root` for remote repos is initially set to the remote URL (for detection and API access purposes) and then updated to the local workspace/clone path during step 3 source resolution
- **Version-to-tag pinning intent:** If `brief.target_version` is absent but `brief.version` is present, record the intent to apply **implicit tag resolution** from `brief.version` when step 3 resolves the source. Do not resolve the tag here — tag resolution runs in step 3 alongside the clone. This step only notes the pinning intent so step 3 knows to attempt it. See `references/source-resolution-protocols.md` → "Implicit Tag Resolution".

**If source_repo is a local path:**
- Verify path exists and contains source files
- Store resolved: local path as `source_root`, file listing

**If source cannot be resolved:**
Halt with: "Source not found: `{source_repo}`. Verify the repository exists and is accessible."

### 5. Report Initialization

Display initialization summary:

"**Forge initialized.**

**Skill:** {name} v{version}
**Source:** {source_repo} @ {branch}
**Language:** {language}
**Scope:** {scope}
**Tier:** {tier} — {tier_description}
**Tools:** {available_tools_list}

Proceeding to ecosystem check..."

Where tier_description follows positive capability framing:
- Quick: "Source reading and spec validation"
- Forge: "AST-backed structural extraction"
- Forge+: "Semantic-guided precision — ccc pre-ranks files before AST extraction"
- Deep: "Full intelligence — structural + contextual + QMD knowledge synthesis"

### 6. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After initialization is complete and all data is loaded (including `target_version` if present in the brief), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices
- Proceed directly to next step after successful initialization
- If any prerequisite check fails, HALT with actionable error — do NOT proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN forge-tier.yaml is loaded, skill-brief.yaml is validated, and source code location is resolved will you proceed to load `{nextStepFile}` for ecosystem check.


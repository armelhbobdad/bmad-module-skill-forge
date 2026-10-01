---
nextStepFile: 'sub/ccc-discover.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
preferencesFile: '{sidecar_path}/preferences.yaml'
# Resolve `{validateBriefSchemaHelper}` to the first existing path; HALT
# (exit code 3, helper-missing) if neither exists. §3 relies on the helper
# for deterministic schema-conformance checks (required fields, regex
# patterns, enum membership, docs-only conditional rules) so this stage
# does not re-run those checks in prose.
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Load Brief

## STEP GOAL:

To load and validate the skill-brief.yaml compilation config, resolve the source code location, and load the forge tier from sidecar to determine available capabilities for the compilation pipeline.

## Rules

- Focus only on loading brief, resolving source, and determining tier — do not begin extraction or compilation
- Write nothing but the brief's run folder (§0), the decisions recorded in it, and `batch_active: false` in `batch-state.yaml` when §2 finds a stale `--batch` checkpoint: this step loads and validates

## MANDATORY SEQUENCE

### 0. Start the Run Folder

Every brief gets a run folder of its own, a `--batch` run's next brief included: the decisions recorded in it and the staged envelope payloads belong to this brief. Create it:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-create-skill-XXXXXXXX"
```

Bind `{run_dir}` ← the path it prints. Step 8 deletes it once the brief finishes; a halted brief keeps it. If it cannot be created, **HARD HALT** (exit code 4, `write-failed`, phase `load-brief`): display "**Create Skill cannot start: the run folder could not be created.** {the first stderr line}" and emit with nothing to stage in:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --target stderr <<'SKF_JSON'
{"phase": "load-brief", "halt_reason": "write-failed", "reason": "<that message, one line>", "summary": {"halt_reason": "write-failed", "evidence_report": null}}
SKF_JSON
```

### 1. Load Forge Tier

Load `{forgeTierFile}` completely.

**If file does not exist:**
**HARD HALT** (exit code 3, `forge-tier-missing`, phase `load-brief`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Forge halted: No forge configuration found. Run [SF] Setup Forge first to detect tools and set your tier."

**If file exists:**
Extract and report:
- `tier`: Quick, Forge, Forge+, or Deep
- `tools`: which tools are available (gh, ast-grep, ccc, qmd)
- `ccc_index`: ccc index state (status, indexed_path, last_indexed) — needed by step 2b

**Apply tier override:** Read `{preferencesFile}`. If `tier_override` is set and is one of the exact valid tier values (`Quick`, `Forge`, `Forge+`, `Deep`), use it instead of the detected tier. **If `tier_override` is set but is not one of those four values:** log a warning — "Unknown tier_override `{value}` in preferences.yaml; falling back to detected tier `{detected_tier}`. Valid values: Quick, Forge, Forge+, Deep." — and use the detected tier. Never silently apply an unknown override value, and never map it heuristically to a tier.

**Record the decision** in the run sink per the Workflow Rules, in every mode, on the valid-override path and on the rejected-override path alike: stage the object as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

- Valid override applied: `{"step": "load-brief", "gate": "tier-override", "decision": "apply", "value": "{tier_override}", "rationale": "explicit preferences.yaml tier_override", "timestamp": "{ISO}"}`
- Invalid override rejected: `{"step": "load-brief", "gate": "tier-override", "decision": "reject-invalid", "value": "{tier_override}", "fallback": "{detected_tier}", "rationale": "tier_override not in Quick, Forge, Forge+, Deep", "timestamp": "{ISO}"}`

Step 5 §7 renders the sink into the evidence report's `## Auto-Decisions` table, so reviewers can audit every silent choice.

### 2. Discover Skill Brief

**If user provided a specific brief path or skill name:**
- If the value looks like a file path (starts with `/`, `./`, `~`, or contains path separators): treat it as a direct file path and load it
- Otherwise, treat it as a skill name and search `{forge_data_folder}/{skill-name}/skill-brief.yaml`
- If found, load it completely

**If user invoked with --batch flag:**
- Check `{sidecar_path}/batch-state.yaml` for an active batch checkpoint:
  - If `batch_active: true`: validate the checkpoint before trusting it — both conditions below must hold:
    1. `0 <= current_index < len(brief_list)` — the index points inside the recorded list.
    2. `os.path.exists(brief_list[current_index])` — the brief file is still on disk.
    If both hold, load the brief at `brief_list[current_index]` (resuming a batch loop from step 8). If **either** check fails, the checkpoint is stale (briefs renamed, moved, or deleted between runs; index off the end after a partial failure). Log a warning — "Stale batch checkpoint — current_index={i}, brief_list length={n}, brief_exists={bool}. Resetting and re-discovering." — then set `batch_active: false` in `batch-state.yaml` and fall through to the no-checkpoint branch below.
  - If no checkpoint exists or `batch_active` is false: search specified directory for all `skill-brief.yaml` files, list discovered briefs with skill names, store list for batch loop processing, and load the FIRST brief

**Bind `{brief_path}`** ← the path of the `skill-brief.yaml` this section loaded: the path given, `{forge_data_folder}/{skill-name}/skill-brief.yaml` for a skill name, or under `--batch` the brief at `brief_list[current_index]` (the first brief discovered on a new batch), never the batch folder. Later steps hand it to their helpers (`--brief`, `amend --target`).

**If no brief found:**
**HARD HALT** (exit code 2, `brief-missing`, phase `load-brief`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "No skill brief found. Run [BS] Brief Skill to create one, or use [QS] Quick Skill for brief-less generation."

### 3. Validate Brief Structure

Resolve `{validateBriefSchemaHelper}` ← first existing path in `{validateBriefSchemaProbeOrder}`. If neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `load-brief`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot validate the brief: skf-validate-brief-schema.py is missing. Re-install SKF, then re-run create-skill."

Run the deterministic schema validator — it checks required fields, regex patterns (`name`, `version`), enum membership (`source_type`, `source_authority`, `forge_tier`, `scope.type`), type correctness, the docs-only conditional rule (`doc_urls` ≥ 1 when `source_type == "docs-only"`), and the version-non-empty-or-whitespace rule:

```bash
uv run {validateBriefSchemaHelper} "{brief_path}"
```

The helper emits:

```json
{
  "valid": <bool>,
  "errors":   [{"field": "...", "message": "Brief validation failed: ..."}, ...],
  "warnings": [{"field": "...", "message": "..."}, ...],
  "halt_reason": "brief-missing" | "brief-malformed" | "brief-invalid" | null,
  "brief": { ...parsed YAML when loadable... }
}
```

**If `valid` is false:** **HARD HALT** (exit code 2, `{halt_reason}`, phase `load-brief`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with the helper's `halt_reason` and the first error's `message` as the halt message, and display that `message` verbatim: the helper already formats messages in the "Brief validation failed: ..." form the user expects. For halt-reasons:

- `brief-missing` — the brief path doesn't exist. Display the helper's message (it includes the `Run [BS] Brief Skill` redirect).
- `brief-malformed` — the YAML failed to parse. Display the helper's message.
- `brief-invalid` — schema or conditional-rule violation. Display the first `errors[].message`. Multiple errors may appear; the user typically fixes one source and re-runs.

**If `valid` is true:** continue with `brief` (the parsed object) for downstream sections. Surface any `warnings[]` to the user but do not halt.

**Field reference (for human readers):**

The complete contract — required fields, optional fields, types, and rules — lives in `src/shared/scripts/schemas/skill-brief.v1.json` and the prose mirror at `src/skf-brief-skill/assets/skill-brief-schema.md`. Read those if you need to explain a specific field; do not restate the rules here.

### 4. Resolve Source Code Location

**If `source_type: "docs-only"`:** Skip source resolution. Set `source_root: null` in context. Proceed directly to section 5 (Report Initialization) — docs-only skills have no source to resolve.

**If source_repo is a GitHub URL or owner/repo format:**
- Verify repository exists via `gh_bridge.list_tree(owner, repo, branch)` — **Tool resolution:** `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1` or direct file listing if local; see `knowledge/tool-resolution.md`
- If branch not specified, detect default branch
- Store resolved: owner, repo, branch, file tree. Note: `source_root` for remote repos is initially set to the remote URL (for detection and API access purposes), and step 3 source resolution then sets it to the private tree it reads the source into, at Forge tier and above
- **Version-to-tag pinning intent:** If `brief.target_version` is absent but `brief.version` is present, record the intent to apply **implicit tag resolution** from `brief.version` when step 3 resolves the source. Do not resolve the tag here — tag resolution runs in step 3 alongside the clone. This step only notes the pinning intent so step 3 knows to attempt it. See `references/source-resolution-protocols.md` → "Implicit Tag Resolution".

**If source_repo is a local path:**
- Verify path exists and contains source files
- Store resolved: local path as `source_root`, file listing

**If source cannot be resolved:**
**HARD HALT** (exit code 3, `source-not-found`, phase `load-brief`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Source not found: `{source_repo}`. Verify the repository exists and is accessible."

### 5. Report Initialization

Display initialization summary:

"**Forge initialized.**

**Skill:** {name} v{version}
**Source:** {source_repo} @ {branch}
**Language:** {language}
**Scope:** {scope}
**Tier:** {tier} — {tier_description}
**Tools:** {available_tools_list}

Proceeding to extraction..."

Where tier_description follows positive capability framing:
- Quick: "Source reading and spec validation"
- Forge: "AST-backed structural extraction"
- Forge+: "AST-backed structural extraction plus ccc semantic discovery"
- Deep: "Full intelligence — structural + contextual + QMD knowledge synthesis"

### 6. Auto-Proceed

No user interaction. After initialization completes and all data is loaded (including `target_version` if present), load `{nextStepFile}`, read it fully, then execute it. A failed prerequisite check above has already halted with an actionable error rather than reaching here.


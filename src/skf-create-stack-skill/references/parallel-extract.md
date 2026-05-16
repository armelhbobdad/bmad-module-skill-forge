---
nextStepFile: 'detect-integrations.md'
enumerateStackSkillsScript: '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Parallel Library Extraction

## STEP GOAL:

For each confirmed dependency, extract key exports, usage patterns, and API surface documentation using tier-dependent tools in parallel.

## Rules

- Extract per-library using subprocess Pattern 4 (parallel) when available; if unavailable, extract sequentially
- Each subprocess returns structured extraction, not raw file contents
- Do not analyze cross-library integrations (Step 05)

## MANDATORY SEQUENCE

### 0. Check Compose Mode

**If `compose_mode` is true:**

"**Extraction data already available from individual skills. Skipping extraction phase.**"

For each confirmed skill, load SKILL.md from the version-aware path resolved in step 2.

**Re-resolve at step 4 entry (S17):** Between step 2 manifest detection and step 4 extraction, a concurrent write could have advanced a skill's `active_version`. On entering this step, re-resolve `skill_package_path` for each confirmed skill via the export-manifest (or symlink fallback) and capture the freshly-read `version` and `metadata_hash` into workflow state. If the `metadata_hash` diverges from the value stored in step 2, log a warning `"constituent '{skill_name}' changed between step 2 and step 4 — using fresh values"` and replace the workflow-state entry (so step 7 provenance records the hash active at extraction time, with the drift logged for audit).

Use `skill_package_path` (stored in step 2 and optionally refreshed above) directly — this already points to the resolved `{skill_package}` or `{active_skill}` directory containing the skill's artifacts. If `skill_package_path` is not available, resolve via the `{active_skill}` template: `{skills_output_folder}/{skill_dir}/active/{skill_dir}/SKILL.md` (see `knowledge/version-paths.md`).

**Exports resolution order (H1) — script-driven:** Do NOT walk per-skill `metadata.json` → `references/` → SKILL.md by hand. Invoke the helper once at step entry to compute the full inventory for every confirmed skill in one deterministic call:

```bash
uv run {enumerateStackSkillsScript} enumerate {skills_output_folder}
```

The script emits JSON of the form:

```json
{
  "skills": [
    {
      "name": "<skill-name>",
      "path": "<rel-to-skills-root, forward-slash>",
      "exports": ["..."],
      "exports_source": "metadata|references|skill-md|unknown",
      "confidence": "T1|T2|T1-low",
      "metadata_hash": "sha256:..." | null
    }
  ],
  "cycles": ["<skill-name>"],
  "warnings": ["<text>"]
}
```

Cache this result as `stack_skill_inventory` in workflow state — the per-skill subagent fan-out at §1+ MUST read from this cache rather than re-reading each skill's `SKILL.md` / `metadata.json` / `references/` to determine exports. Append every entry in `warnings[]` to workflow state for the evidence report (the script already labels them per-skill, e.g. `"<skill-name>: no exports found via any resolution path"`). For every entry in `cycles[]`, halt with a structured-error contract on stderr — a composes-cycle makes the stack unbuildable.

Build a `per_library_extractions[]` entry for each skill by reading from the cached inventory:
- `library`: `inventory.skills[i].name`
- `exports`: `inventory.skills[i].exports`
- `exports_source`: `inventory.skills[i].exports_source` (one of `metadata|references|skill-md|unknown` — capture for step 7 provenance)
- `confidence`: `inventory.skills[i].confidence` (one of `T1|T2|T1-low`; `unknown` source ⇒ `T1-low`). Do not silently drop T3 evidence; carry whatever tier the source skill declared if §1+ subagent analysis upgrades the value.
- `metadata_hash`: `inventory.skills[i].metadata_hash` — record for step 7 provenance (null when exports came from references/ or SKILL.md prose).
- `usage_patterns`: populated by the §1+ per-skill subagent fan-out, NOT by this script. The script provides the inventory + exports; the subagent does the per-skill usage analysis. They're complementary.

Display an extraction summary:

"**Loaded {N} skill extractions from existing skills.**

| Skill | Exports | Confidence | Status |
|-------|---------|------------|--------|
| {name} | {count} | {tier} | Loaded |"

Auto-proceed to next step.

**If not compose_mode:** Continue with section 1 (existing flow).

### 1. Prepare Extraction Plan

**AST Tool Availability Check (Forge/Deep only):**

This workflow operates on local project files and installed library packages. Remote source resolution does not apply — libraries are analyzed as they exist within the project's dependency tree.

**If AST tool is unavailable at Forge/Deep tier:**

⚠️ **Warn the user explicitly:** "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**Per-file AST failure handling:**

If ast-grep fails on an individual file (parse error, unsupported syntax), fall back to source reading for that file only. Label the affected file's results T1-low; unaffected files retain T1. Log a warning noting which file degraded and why.

For each library in `confirmed_dependencies`, determine extraction strategy based on forge tier:

**Quick Tier:**
- Read source files that import the library
- Extract usage patterns from import statements and function calls
- Identify key exports used in this project
- Confidence: T1-low (source reading inference)

**Forge Tier (adds to Quick):**
- Use ast_bridge to analyze structural exports from library source
- Extract function signatures, type definitions, class hierarchies
- Map parameter types and return types
- Confidence: T1 (AST-verified structural extraction)

**Deep Tier (adds to Forge):**
- Perform all Forge tier extractions (T1)
- Additionally: query existing QMD temporal collections for each library
- Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`
- For each library in `confirmed_dependencies`, search for a registry entry where `skill_name` matches the library name AND `type` is `"temporal"`
- **If a matching temporal collection exists:**
  - Query `qmd_bridge.search("{library_name} deprecated OR removed OR breaking change")` for deprecation context
  - Query `qmd_bridge.search("{library_name} migration OR upgrade")` for migration patterns
  - Query `qmd_bridge.search("{library_name} version issue OR bug OR workaround")` for version-specific warnings
  - **Tool resolution for qmd_bridge:** Use QMD MCP tools — `mcp__plugin_qmd-plugin_qmd__search` (Claude Code), qmd MCP server (Cursor), `qmd search "{query}"` (CLI). See `knowledge/tool-resolution.md`
  - Classify each result as T2-past (historical) or T2-future (planned changes) per confidence-tiers.md
  - Append temporal findings to the library's extraction as T2 annotations with `[QMD:{collection}:{doc}]` citations
- **If no matching temporal collection found:**
  - Log: "No temporal collection for {library_name}. T2 enrichment skipped."
  - Continue with T1/T1-low extraction only
- Confidence: T1 for structural (AST), T2 for temporal annotations (QMD-enriched)

### 2. Launch Parallel Extraction

**Launch subprocesses in parallel** (max_parallel_generation: 3–5 concurrent Agent tool calls in Claude Code, IDE-dependent in Cursor, CPU core count in CLI) — one per confirmed library:

Each subprocess:
1. Reads all files importing the library (from step 03 file lists)
2. Extracts key exports used in this project (functions, classes, types, constants)
3. Identifies usage patterns (initialization, configuration, common call patterns)
4. Labels confidence tier based on extraction method
5. Returns structured extraction to parent:

```
{
  library: "name",
  version: "from_manifest",
  exports_found: ["fn1", "fn2", "Type1"],
  usage_patterns: ["pattern description with file:line"],
  confidence: "T1|T1-low|T2|T3",
  files_analyzed: count,
  warnings: [],
  temporal: {
    deprecated_exports: ["export_name — reason [QMD:collection:doc]"],
    migration_notes: ["note [QMD:collection:doc]"],
    version_warnings: ["warning [QMD:collection:doc]"],
    t2_annotation_count: count
  }
}
```

**If parallel subprocess unavailable:** Process libraries sequentially in main thread. Report progress after each library.

**Per-subprocess timeout (S6):** Apply a 60-second wall-clock timeout to each library's extraction subprocess. On timeout, mark the library as `partial-failure` with `warnings: ["extraction timeout after 60s"]`, store whatever partial data was returned (if any), and continue with the remaining libraries. Do NOT abort the batch on a single timeout.

### 3. Handle Extraction Failures

For each library extraction:

**Success:** Store extraction result.

**Partial failure:** Store partial result with warnings, continue with other libraries.

**Complete failure:** Log failure reason, exclude from stack skill, note in report.

"**Warning:** Extraction failed for {library}: {reason}. Excluding from stack skill."

**If ALL extractions fail:** HALT — cannot produce meaningful stack skill. Before halting (B7):

1. Purge any in-flight staging artifacts under the forge workspace: remove `{forge_data_folder}/{project_name}-stack/{version}/*-tmp` and any `{forge_data_folder}/{project_name}-stack/{version}/*.skf-tmp` directories so partial state does not linger.
2. Emit a structured error contract on stderr: `{"status":"error","skill":"skf-create-stack-skill","stage":"step 4","reason":"all extractions failed","libraries":[...]}`.
3. Exit with a non-zero status so headless pipelines detect the failure.

### 4. Display Extraction Summary

"**Library extraction complete.**

| Library | Exports | Patterns | Confidence | Status |
|---------|---------|----------|------------|--------|
| {name} | {count} | {count} | {tier} | ✓ |
| {name} | {count} | {count} | {tier} | ✓ |
| {name} | — | — | — | ⚠ partial |

**Results:** {success_count}/{total_count} libraries extracted
**Confidence distribution:** T1: {count}, T1-low: {count}, T2: {count}
{If Deep tier:} **T2 enrichment:** {enriched_count}/{total_count} libraries had temporal collections available
{If libraries without temporal > 0:} **Tip:** Run [CS] Create Skill at Deep tier for individual libraries to generate temporal collections, then re-run [SS] for full T2 enrichment.
{If warnings:} **Warnings:** {warning_count} issues noted

**Proceeding to integration detection...**"

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


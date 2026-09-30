---
nextStepFile: 'detect-integrations.md'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Parallel Library Extraction

## STEP GOAL:

For each confirmed dependency, extract key exports, usage patterns, and API surface documentation using tier-dependent tools in parallel.

## Rules

- Extract per-library using subprocess Pattern 4 (parallel) when available; if unavailable, extract sequentially
- Each subprocess returns structured extraction, not raw file contents
- Label each export by the tool that read it, never by the forge tier
- Do not analyze cross-library integrations (Step 05)

## MANDATORY SEQUENCE

### 0. Check Compose Mode

**If `compose_mode` is true:**

"**Extraction data already available from individual skills. Skipping extraction phase.**"

For each confirmed skill, load SKILL.md from its `skill_package_path` (step 2, refreshed below).

**Re-resolve at step 4 entry (S17):** a concurrent write could have advanced a skill's version between step 2 and step 4. Re-resolve each confirmed skill from this step's helper result below: the `skills[]` entry whose `name` is its `skill_dir` gives the fresh `skill_package_path` (`{skills_output_folder}/{path}`) and `metadata_hash`. If the `metadata_hash` diverges from the value stored in step 2, log a warning `"constituent '{skill_name}' changed between step 2 and step 4 — using fresh values"` and replace the workflow-state entry (so step 7 provenance records the hash active at extraction time, with the drift logged for audit). If a confirmed skill has no `skills[]` entry now, emit the result envelope on stderr per the Result Contract in SKILL.md and exit `3` (`resolution-failure`), naming it: "constituent `{skill_dir}` is no longer an SKF skill package — re-run [SS]." Use the same envelope as the composes-cycle halt below.

Use `skill_package_path` directly — it points to the package the helper resolved.

**Exports resolution order (H1) — script-driven:** Do NOT walk per-skill `metadata.json` → `references/` → SKILL.md by hand. Invoke the helper once at step entry to compute the full inventory for every confirmed skill in one deterministic call:

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. HALT if no candidate exists.

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder}
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
      "evidence_tier": "T1|T1-low|T2|T3",
      "metadata_hash": "sha256:..."
    }
  ],
  "cycles": ["<skill-name>"],
  "warnings": ["<text>"],
  "not_skf_output": ["<skill-name>"]
}
```

Cache this result as `stack_skill_inventory` in workflow state — the per-skill subagent fan-out at §1+ MUST read from this cache rather than re-reading each skill's `SKILL.md` / `metadata.json` / `references/` to determine exports. Append to workflow state the `warnings[]` entries that name a confirmed skill (each starts with `<skill_dir>: `, e.g. `"<skill-name>: no exports found via any resolution path"`) for the evidence report. If `cycles[]` names a confirmed skill, a composes-cycle makes the stack unbuildable — emit the result envelope on stderr per the Result Contract in SKILL.md and exit `3`:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":"compose","exit_code":3,"halt_reason":"resolution-failure"}
```

Build a `per_library_extractions[]` entry for each confirmed skill, from the `skills[]` entry whose `name` is its `skill_dir`:
- `library`: `inventory.skills[i].name`
- `exports`: `inventory.skills[i].exports`
- `exports_source`: `inventory.skills[i].exports_source` (one of `metadata|references|skill-md|unknown` — capture for step 7 provenance)
- `confidence`: `inventory.skills[i].evidence_tier` (one of `T1|T1-low|T2|T3`), the library's tier, which steps 5 and 7 read. Never `inventory.skills[i].confidence`: it only says where the export list came from.
- `metadata_hash`: that entry's `metadata_hash` — the digest of the package's `metadata.json`, recorded for step 7 provenance.
- `usage_patterns`: populated by the §1+ per-skill subagent fan-out, NOT by this script. The script provides the inventory + exports; the subagent does the per-skill usage analysis. They're complementary.

Report the loaded extractions — for each skill: export count, confidence tier, and load status. Then auto-proceed to the next step.

**If not compose_mode:** Continue with section 1 (existing flow).

### 1. Prepare Extraction Plan

**Export labels, at every tier:**

- An export an ast-grep rule matched: `extraction_method: "ast_bridge"`, `confidence: "T1"`, `signature_source: "T1"`.
- An export read by eye, for any reason (Quick tier, ast-grep unavailable, a file ast-grep could not parse, a rule that matched nothing, or a file read instead of running a rule): `extraction_method: "source_reading"`, `confidence: "T1-low"`, `signature_source: "T1-low"`.

Deep-tier temporal findings are T2 annotations, never export labels.

**AST Tool Availability Check (Forge/Deep only):**

This workflow operates on local project files and installed library packages. Remote source resolution does not apply — libraries are analyzed as they exist within the project's dependency tree.

**If AST tool is unavailable at Forge/Deep tier:**

⚠️ **Warn the user explicitly:** "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**Per-file AST failure handling:**

If ast-grep fails on an individual file (parse error, unsupported syntax), fall back to source reading for that file only, and log a warning noting which file degraded and why.

For each library in `confirmed_dependencies`, determine extraction strategy based on forge tier:

**Quick Tier:**
- Read source files that import the library
- Extract usage patterns from import statements and function calls
- Identify key exports used in this project

**Forge Tier (adds to Quick):**
- Use ast_bridge to analyze structural exports from library source
- Extract function signatures, type definitions, class hierarchies
- Map parameter types and return types

**Deep Tier (adds to Forge):**
- Perform all Forge tier extractions
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

### 2. Launch Parallel Extraction

**Launch subprocesses in parallel** (max_parallel_generation: 3–5 concurrent Agent tool calls in Claude Code, IDE-dependent in Cursor, CPU core count in CLI) — one per confirmed library:

Each subprocess:
1. Reads all files importing the library (from step 03 file lists)
2. Extracts key exports used in this project (functions, classes, types, constants)
3. Identifies usage patterns (initialization, configuration, common call patterns)
4. Labels each export by the tool that read it (§1)
5. Returns structured extraction to parent, one record per export:

```
{
  library: "name",
  version: "from_manifest",
  exports: [
    {
      export_name: "fn1",
      export_type: "function|class|type|constant",
      params: ["typed param strings"],
      return_type: "type",
      source_file: "path relative to {scan_root}",
      source_line: 0,
      extraction_method: "ast_bridge|source_reading",
      confidence: "T1|T1-low",
      signature_source: "T1|T1-low"
    }
  ],
  usage_patterns: ["pattern description with file:line"],
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

`{scan_root}` is the project root, `project_root` from step 1: `source_file` is relative to it, with forward slashes (a library installed outside it, in a global site-packages say, is relative to its install folder, and step 7 warns on it). `source_line` is the export's `def`, `class` or declaration line, not a decorator above it. The subprocess returns no library tier: §3a sets it.

**If parallel subprocess unavailable:** Process libraries sequentially in main thread. Report progress after each library.

**Per-subprocess timeout (S6):** Apply a 60-second wall-clock timeout to each library's extraction subprocess. On timeout, mark the library as `partial-failure` with `warnings: ["extraction timeout after 60s"]`, store whatever partial data was returned (if any), and continue with the remaining libraries. Do NOT abort the batch on a single timeout.

### 3. Handle Extraction Failures

For each library extraction:

**Success:** Store the extraction result as the library's `per_library_extractions[]` entry.

**Partial failure:** Store partial result with warnings, continue with other libraries.

**Complete failure:** Log failure reason, exclude from stack skill, note in report.

"**Warning:** Extraction failed for {library}: {reason}. Excluding from stack skill."

**If ALL extractions fail:** HALT — cannot produce meaningful stack skill. Before halting (B7):

1. Purge any in-flight staging artifacts under the forge workspace: remove `{forge_data_folder}/{project_name}-stack/{version}/*-tmp`, any `{forge_data_folder}/{project_name}-stack/{version}/*.skf-tmp` directories and the §3a labels file `{forge_data_folder}/{project_name}-stack.skf-labels.json` so partial state does not linger.
2. Emit the result envelope on stderr per the Result Contract in SKILL.md (`stack_libraries` carries the confirmed library names that failed extraction), and exit `2`:

   ```
   SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":["<confirmed-lib>", "..."],"mode":"{code|compose}","exit_code":2,"halt_reason":"all-extractions-failed"}
   ```

### 3a. Check the Export Labels

Code mode only (compose mode leaves this step at §0). Steps 5 to 7 read the labels checked here. Resolve `{renderMetadataStatsHelper}` from `{renderMetadataStatsProbeOrder}`; if neither path exists, append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "label-check-skipped"`, `message`: the reason) and go to the library tiers below.

Write every export record, each with `source_library` set to its library, as `{"entries": [...]}` to `{forge_data_folder}/{project_name}-stack.skf-labels.json`, and run:

```bash
echo '{}' | uv run {renderMetadataStatsHelper} {forge_data_folder}/{project_name}-stack.skf-labels.json --shape stack
```

Rely on its JSON, not the exit code, and write neither its `stats` nor its `confidence_distribution` into `metadata.json`. If it exits `2` (no JSON), append a `label-check-skipped` entry with its stderr as the message, delete the file and go to the library tiers. Otherwise fix each `coherence` violation in the stored records:

- **`provenance.entries[<i>].<field>`:** set that field of record `<i>` to the violation's `expected` value and keep its `extraction_method`, which names the tool that read the export. When the violation is on `extraction_method` itself (unknown or missing), set `ast_bridge` only when an ast-grep rule matched the export, `source_reading` otherwise.
- **`confidence_distribution`:** some records carry no valid `signature_source`: set `T1` on each such `ast_bridge` record and `T1-low` on each such `source_reading` record.

Rewrite the file and run the helper again until `coherence.ok` is true, keep that run's `confidence_distribution` as §4's export label counts, and delete the file. When a record changed, append one `workflow_warnings[]` entry (`step: "step-04"`, `severity: "info"`, `code: "export-labels-relabeled"`) naming each relabeled export and its library.

**Library tiers.** Set each library's `per_library_extractions[].confidence`: `T1` when it has export records and every one is `ast_bridge`, `T1-low` otherwise. Step 5 takes each integration's tier from it, and step 7 bins each library once by it.

### 4. Display Extraction Summary

Report the extraction results: per library the export count, pattern count, confidence tier, and success/partial status; the overall `{success_count}/{total_count}` extracted; the number of libraries at each tier (the unit of `metadata.json`'s `confidence_distribution`); and the export label counts §3a kept. At Deep tier, add the T2-enrichment count (`{enriched_count}/{total_count}` libraries with temporal collections available); and if any library lacked a temporal collection, add the tip: run **[CS] Create Skill** at Deep tier for those libraries to generate temporal collections, then re-run **[SS]** for full T2 enrichment. Note any warning count.

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


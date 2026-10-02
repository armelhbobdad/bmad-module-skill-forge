---
nextStepFile: 'detect-integrations.md'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
renderStackMetadataProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-stack-metadata.py'
  - '{project-root}/src/shared/scripts/skf-render-stack-metadata.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
exportRecordsFile: '{run_dir}/export-records.json'
importCountsFile: '{run_dir}/import-counts.json'
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

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

**Extraction bundle.** What this step extracts goes to `{bundleFile}`, so no later step works from memory: step 5 reads each library's tier there and adds the pairs it keeps, step 6 compiles from it, and step 7 writes the reference files, `metadata.json` and the provenance map from it. It is one JSON object, written with the run's other files in `{run_dir}`:

```json
{
  "mode": "code|compose",
  "scope": ["<confirmed library>"],
  "per_library_extractions": [
    {"library": "<name>", "status": "success|partial", "version": "<version>",
     "confidence": "T1|T1-low|T2|T3", "files_analyzed": 0,
     "usage_patterns": ["<pattern with file:line>"], "warnings": [], "temporal": {}}
  ],
  "failed": [{"library": "<name>", "reason": "<why>"}],
  "integrations": [],
  "hubs": [],
  "cross_cutting": []
}
```

`scope` is step 3's `confirmed_dependencies`; step 5 fills `integrations`, `hubs` and `cross_cutting`. A compose-mode entry also holds `skill_dir`, `skill_package_path`, `exports`, `exports_source`, `source_authority` and `metadata_hash` (§0). A code-mode entry also holds `file_count`, the library's step 3 import count, and its export records sit beside the bundle in `{exportRecordsFile}` (§3a).

### 0. Check Compose Mode

**If `compose_mode` is true:**

"**Extraction data already available from individual skills. Skipping extraction phase.**"

For each confirmed skill, load SKILL.md from its `skill_package_path` (step 2, refreshed below): its usage patterns come from there.

**Re-resolve at step 4 entry (S17):** a concurrent write could have advanced a skill's version between step 2 and step 4. Re-resolve each confirmed skill from this step's helper result below: the `skills[]` entry whose `name` is its `skill_dir` gives the fresh `skill_package_path` (`{skills_output_folder}/{path}`) and `metadata_hash`. **The provenance anchor (S13) is the hash of the package this step reads**: step 2's value, unless the package changed since. When the `metadata_hash` diverges from the value step 2 stored, append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "constituent-changed"`, `message`: "constituent '{skill_name}' changed between step 2 and step 4: using fresh values") and replace the workflow-state entry. Step 7 writes the bundle's `metadata_hash` into `constituents[].metadata_hash` and never hashes again. If a confirmed skill has no `skills[]` entry now, HALT (exit 3, `halt_reason: "resolution-failure"`, phase `parallel-extract:constituent-gone`) with "constituent `{skill_dir}` is no longer an SKF skill package: re-run [SS]."

Use `skill_package_path` directly — it points to the package the helper resolved.

**Exports resolution order (H1), script-driven:** Do NOT walk per-skill `metadata.json` → `references/` → SKILL.md by hand. Invoke the helper once at step entry to compute the full inventory for every confirmed skill in one deterministic call:

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `parallel-extract:enumerate`) with "**Cannot proceed.** `skf-enumerate-stack-skills.py` is missing, so no constituent's exports can be read. Re-install SKF, then re-run."

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

Cache this result as `stack_skill_inventory` in workflow state: each constituent's exports come from it, never from re-reading its `SKILL.md`, `metadata.json` or `references/`. Append to `workflow_warnings[]` the `warnings[]` entries that name a confirmed skill (each starts with `<skill_dir>: `, e.g. `"<skill-name>: no exports found via any resolution path"`). If `cycles[]` names a confirmed skill, a composes-cycle makes the stack unbuildable: HALT (exit 3, `halt_reason: "resolution-failure"`, phase `parallel-extract:cycle`) with "composes cycle among the confirmed skills: {the `cycles[]` names}."

Build a `per_library_extractions[]` entry for each confirmed skill, from the `skills[]` entry whose `name` is its `skill_dir`:
- `library`: `inventory.skills[i].name`
- `exports`: `inventory.skills[i].exports`
- `exports_source`: `inventory.skills[i].exports_source` (one of `metadata|references|skill-md|unknown` — capture for step 7 provenance)
- `confidence`: `inventory.skills[i].evidence_tier` (one of `T1|T1-low|T2|T3`), the library's tier, which steps 5 and 7 read. Never `inventory.skills[i].confidence`: it only says where the export list came from.
- `metadata_hash`: that entry's `metadata_hash`, the provenance anchor above.
- `skill_dir`, `skill_package_path`, `version` and `source_authority`: from step 2's entry, the path refreshed above.
- `usage_patterns`: read from the constituent's `SKILL.md` loaded above, each with the file and line it cites there.

Write `{bundleFile}`: `mode`, `scope` and these entries. Then report the loaded extractions: for each skill, export count, confidence tier, and load status. Then auto-proceed to the next step.

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

Degrade to Quick tier extraction, and append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "ast-degraded"`, `message`: the tier and the reason), which the evidence report lists.

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
1. Reads all files importing the library (its `files[]` in `{importCountsFile}`, step 3's import counts, whose paths are relative to `{project_root}`, as `source_file` is)
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
      source_file: "path relative to {project_root}",
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

`{project_root}` is the project root, `project_root` from step 1, whatever folder `{scan_root}` narrowed steps 2, 3 and 5 to: `source_file` is relative to it, with forward slashes (a library installed outside it, in a global site-packages say, is relative to its install folder, and step 7 warns on it). `source_line` is the export's `def`, `class` or declaration line, not a decorator above it. The subprocess returns no library tier: §3a sets it.

**If parallel subprocess unavailable:** Process libraries sequentially in main thread. Report progress after each library.

**Per-subprocess timeout (S6):** Apply a 60-second wall-clock timeout to each library's extraction subprocess. On timeout, mark the library as `partial-failure` with `warnings: ["extraction timeout after 60s"]`, store whatever partial data was returned (if any), and continue with the remaining libraries. Do NOT abort the batch on a single timeout.

### 3. Handle Extraction Failures

For each library extraction:

**Success:** Store the extraction result as the library's `per_library_extractions[]` entry.

**Partial failure:** Store partial result with warnings, continue with other libraries.

**Complete failure:** Log failure reason, exclude from stack skill, note in report.

"**Warning:** Extraction failed for {library}: {reason}. Excluding from stack skill."

Record each excluded library in the bundle's `failed[]` and append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "extraction-failed"`, `message`: the library and the reason).

**If ALL extractions fail:** HALT (exit 2, `halt_reason: "all-extractions-failed"`, phase `parallel-extract:all-failed`, `stack_libraries` the confirmed library names that failed): nothing remains to build a stack from (B7). The run folder stays, as after every halt but a cancel: its `warnings.jsonl` holds the `extraction-failed` entry that says why each library failed.

**Otherwise** write `{bundleFile}`: `mode`, `scope`, one `per_library_extractions[]` entry per library that returned (each export record moves to `{exportRecordsFile}` in §3a, so the entry keeps none) and `failed[]`.

### 3a. Check the Export Labels

Code mode only (compose mode leaves this step at §0). Steps 5 to 7 read the labels checked here, from the file this section writes and keeps for the rest of the run.

Write every export record, each with `source_library` set to its library, as `{"entries": [...]}` to `{exportRecordsFile}`. Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `parallel-extract:library-tiers`) with "**Cannot proceed.** `skf-render-stack-metadata.py` is missing, so no export label can be checked and no library tier set. Re-install SKF, then re-run." Otherwise relabel the records:

```bash
uv run {renderStackMetadataHelper} relabel --records "{exportRecordsFile}"
```

Keep its `confidence_distribution` (one count per record, never `metadata.json`'s) as §4's export label counts. When its `relabeled[]` is not empty, append one `workflow_warnings[]` entry (`step: "step-04"`, `severity: "info"`, `code: "export-labels-relabeled"`) naming each relabeled export and its library. When it exits `1` (a violation it could not fix, in its `coherence.violations[]`) or `2` (no JSON: its stderr says why), append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "label-check-skipped"`, `message`: those violations or its stderr) and go on.

**Library tiers.** Run the same helper on the checked records, with every library of the bundle's `per_library_extractions[]`, comma-separated:

```bash
uv run {renderStackMetadataHelper} library-tiers --records "{exportRecordsFile}" --libraries "<names>"
```

Set each library's `per_library_extractions[].confidence` in `{bundleFile}` to its `tier`, the helper's one rule for a code-mode library. On exit `2` its stderr names the input it refused, such as a record whose `source_library` is not a stack library: fix the record or the list and run it again. Step 5 takes each integration's tier from these tiers, and step 7 bins each library once by them.

### 4. Display Extraction Summary

Report the extraction results from `{bundleFile}`: per library the export count, pattern count, confidence tier, and success/partial status; the overall `{success_count}/{total_count}` extracted; the number of libraries at each tier (the unit of `metadata.json`'s `confidence_distribution`); and the export label counts §3a kept. At Deep tier, add the T2-enrichment count (`{enriched_count}/{total_count}` libraries with temporal collections available); and if any library lacked a temporal collection, add the tip: run **[CS] Create Skill** at Deep tier for those libraries to generate temporal collections, then re-run **[SS]** for full T2 enrichment. Note any warning count.

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.


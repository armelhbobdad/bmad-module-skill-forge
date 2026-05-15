---
nextStepFile: 'merge.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
extractionPatternsTracingData: 'skf-create-skill/references/extraction-patterns-tracing.md'
remoteSourceResolutionData: 'references/remote-source-resolution.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 02, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 04.

## Rules

- Focus only on extracting changed exports — do not merge or modify existing skill
- Only extract files in the change manifest — do not touch unchanged files. **Exception (gap-driven mode):** §0a's Targeted Re-Extraction Branch also scans files listed in each manifest entry's `remediation_paths[]` to resolve citation-less Critical/High gaps.
- For each changed file, launch a subprocess for deep AST analysis (Pattern 2); if unavailable, extract sequentially

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 0. Check for Gap-Driven Mode

**If `update_mode == "gap-driven"` (set in step 1 via `--from-test-report`, confirmed in step 2 section 0):**

Source code has not drifted — the gap-derived manifest from step 2 contains export-level findings translated from the test report, not file-level changes. Perform citation spot-checks instead of full re-extraction to verify each gap-affected export is still at its recorded location.

**0.a Pre-flight: verify workspace HEAD matches pinned commit.** Gap-driven spot-checks read source at recorded `source_line` positions and must see the exact bytes the skill was pinned against. A drifted workspace silently verifies against the wrong tree — moved/renamed symbols appear "verified" because the recorded line now points at different code. Before reading any source, run this guard:

- Resolve `pinned_commit` from `metadata.source_commit` (loaded in step 1).
- **If `pinned_commit` is null, empty, `"local"`, or a per-repo map (stack skills) with no single commit:** skip the guard and log `workspace_drift_check: skipped (no pinned commit)`. Continue to bullet 1.
- **If `source_root` is not a git working tree** (e.g., bare checkout, tarball extract) — detect by running `git -C "{source_root}" rev-parse --is-inside-work-tree`; non-zero exit means skip: log `workspace_drift_check: skipped (not a git working tree)`. Continue to bullet 1.
- **Otherwise** run `git -C "{source_root}" rev-parse HEAD` and compare to `pinned_commit`. Accept either a full SHA match or a short-SHA prefix match (the pinned commit is often stored as an 8-char short hash — see `src/knowledge/provenance-tracking.md`).
  - **On match:** log `workspace_drift_check: ok ({short_sha})` and continue.
  - **On mismatch, AND the user did not pass `--allow-workspace-drift`:** HALT immediately with exit status `halted-for-workspace-drift`. Display:

    ```
    Workspace HEAD does not match the commit this skill was pinned against.

      pinned (metadata.source_commit): {pinned_commit}
      pinned ref (metadata.source_ref): {source_ref or "unset"}
      workspace HEAD ({source_root}):  {head_sha}

    Gap-driven spot-checks read source at pinned line numbers — verifying
    against a drifted tree silently produces wrong results (symbols appear at
    unintended locations). Re-sync the workspace before re-running:

      git -C "{source_root}" checkout {source_ref or pinned_commit}

    Or, to intentionally proceed against the current workspace HEAD (accepting
    that spot-checks will read bytes that differ from the pinned commit),
    re-run update-skill with `--allow-workspace-drift`.
    ```

    Do not proceed to bullet 1. Step-04 merge has not run; no partial writes.
  - **On mismatch WITH `--allow-workspace-drift`:** log `workspace_drift_check: overridden (pinned={pinned_commit}, head={head_sha})` and surface a visible warning in the final report ("**Workspace drift accepted via --allow-workspace-drift** — spot-checks read HEAD {head_sha}, not pinned {pinned_commit}"). Continue to bullet 1. The override does not automatically re-pin `metadata.source_commit`; re-pinning is explicit user work (run the normal-mode update-skill flow against the same HEAD, or re-create the skill).

1. Use the provenance map already loaded in step 1 (at `{forge_version}/provenance-map.json`) — do not re-read
2. For each entry in the gap-derived change manifest from step 2:
   - Look up the export by `name` in `provenance_map.exports` — read `source_file` and `source_line`
   - **If export not found in provenance map:**
     - **If the manifest entry has a `source_citation` (propagated from the test report by step 2 §0 bullet 4):** read the file at that citation's `file:line ± 5` lines and verify the symbol name still appears within that window. Record a full `verified` / `moved` / `missing` entry using the citation as the starting location — same spot-check logic as the "export found" branch below, keyed on the manifest-supplied citation instead of the provenance map. The export is still flagged `NEW_EXPORT` for the merge step; this branch only upgrades the provenance entry from `unknown` to a live spot-check result so step 6 writes `source_file` / `source_line` instead of `null`.
     - **If the manifest entry has no `source_citation` but has a non-empty `remediation_paths[]` AND `severity` is `Critical` or `High`:** route this entry to §0a (Targeted Re-Extraction Branch). §0a scans the remediation paths with the tier-appropriate extractor and, on success, records a full verification record with `verification: re-extracted`, a live `provenance_citation`, and full signature/params/return-type fields for the merge step to consume as a NEW_EXPORT. On failure, §0a halts the workflow — Critical/High gaps are not allowed to degrade to `unknown`. See §0a for the procedure, the consolidated halt protocol, and the output record shape.
     - **If the manifest entry has no `source_citation` AND (`remediation_paths[]` is empty OR `severity` is `Medium`, `Low`, or `Info`):** record as new (`provenance_citation: unknown`) — no spot-check possible; flag for merge step to handle as `NEW_EXPORT`. Step-06 §3 only accepts null `source_file` / `source_line` for these lower-severity unknowns; a Critical/High unknown reaching step 6 indicates §0a was skipped or bypassed and is a workflow bug.
   - **If export found:** read the source file at `source_line ± 5` lines and verify the symbol name still appears within that window
   - Record verification outcome: `verified` (symbol at recorded line), `moved` (symbol found elsewhere in same file — record new line), `missing` (symbol not found in file), `re-extracted` (resolved via §0a from `remediation_paths[]`), or `unknown` (no usable provenance data)
3. Build a minimal extraction results block matching section 4's shape, with `mode: gap-driven` and per-export verification records:

   ```
   Extraction Results:
     mode: gap-driven
     files_extracted: {count}  # non-zero only when §0a scanned remediation_paths[]
     exports_extracted: {gap_count}
     confidence_breakdown:
       T1: {verified_count + moved_count + re_extracted_t1_count}
       T1-low: {re_extracted_t1_low_count}
       T2: 0

     Per-export verification:
       {export_name}:
         provenance_citation: {source_file}:{source_line}
         verification: verified|moved|missing|unknown|re-extracted
         new_location: {source_file}:{new_line}  # set when moved OR re-extracted
         resolution_source: remediation-paths    # set only when verification == re-extracted
         gap_category: NEW_EXPORT|MODIFIED_EXPORT|metadata_update

     Per-file extractions:   # populated only when §0a produced re-extracted records
       {file_path}:
         exports:
           - name: {export_name}
             type: function|class|type|constant
             signature: {full signature}
             location: {file}:{start_line}-{end_line}
             confidence: T1|T1-low
             params: [{name, type}]
             return_type: {type}
             docstring: {summary}
   ```

4. Set `no_reextraction: true` in workflow context — step 6 will use this flag to skip stale `source_file`/`source_line`/`confidence` field updates for `verified` exports. `moved` exports get updated citations; `re-extracted` exports get full fresh provenance from §0a's extraction records (see step 6 §3). The flag is a global gap-driven marker, not a per-entry one — step 6 dispatches on each verification outcome independently.
5. **Skip all remaining sections of step 3** — sections 1–5 are source-drift extraction paths that do not apply. Display the summary below and load `{nextStepFile}` to proceed directly to the merge step.

"**Gap-driven re-extraction.** Verified {verified_count}/{gap_count} citations against live source. Moved: {moved_count}. Missing: {missing_count}. Re-extracted (via remediation paths, §0a): {re_extracted_count}. Unknown (not in provenance map): {unknown_count}. Proceeding to merge."

**If normal mode (`update_mode` unset or not `gap-driven`):** Continue with docs-only check and source extraction below.

### 0a. Targeted Re-Extraction Branch (Helper — Called from §0 bullet 2)

**Do not execute this section sequentially.** It is a helper procedure invoked by §0 bullet 2 when specific conditions are met (see below). Normal-mode runs, and gap-driven runs where every entry has a `source_citation` or qualifies as `Medium`/`Low`/`Info` unknown, skip this section entirely. §0's "skip sections 1–5" instruction does not apply here — §0a is addressed by name from §0, not by sequential fall-through.

**Used by:** §0 bullet 2, when a manifest entry has no `source_citation`, has non-empty `remediation_paths[]`, and `severity` is `Critical` or `High`.

**Purpose:** produce AST-backed provenance for citation-less Critical/High gaps so step 6 §3 never writes `source_file: null` for blocking findings. Honors the workflow-level rule **Never hallucinate — every statement must have AST provenance** against the most common gap-driven trigger — a failing test report whose Gap Report `Source:` field is a region reference (e.g., `@storybook/addon-docs control primitives`) rather than a `file:line` pair. Gap-driven mode skips §1 through §5, so §0a is also the only place §1b's source-access and extraction machinery is invoked during gap-driven runs.

**Procedure:**

1. **Resolve source access** — invoke §1b's MCP-fallback chain (gh API → zread → deepwiki → workspace / ephemeral clone) once per workflow run to ensure files under `{source_root}` are readable. Cache the chosen access path; do not re-resolve per entry.
2. **Expand `remediation_paths[]`** — for each path across all qualifying entries:
   - Literal source file (ends in a recognized source extension): use as-is.
   - Directory or glob: expand under `{source_root}` using the provenance map's file patterns.
   - **Security boundary:** reject and skip any path that resolves outside `{source_root}`. Remediation text is user-editable and must never be allowed to escape the source tree.
   - Deduplicate the resolved file set across all entries routed to §0a — each physical file is scanned at most once.
3. **Extract** — run the tier-appropriate extractor from §1b (Quick pattern-match → T1-low; Forge/Forge+/Deep AST via ast-grep → T1) over the resolved file set. Launch subprocesses in parallel (Pattern 4) when available; sequential fallback otherwise. Follow the AST Extraction Protocol in `{extractionPatternsData}` for Forge/Deep tiers, and the tier-degradation rules in `{tierDegradationRulesData}` when AST tools fail on individual files.
4. **Match by name** — for each manifest entry routed here, search the aggregated extraction results for an export whose `name` matches the manifest entry's `name`. Record the first hit as:
   - `verification: re-extracted`
   - `provenance_citation: {file}:{start_line}` from the AST result
   - `new_location: {file}:{start_line}` (same value — satisfies the existing consumer contract)
   - `resolution_source: remediation-paths`
   - `confidence: T1` (AST-extracted) or `T1-low` (pattern-matched fallback)
   - the full extraction signature (type, params, return_type, docstring) — mirror the shape of §4's per-file extraction record so step 4 Priority 5 can merge it with the same code path used in normal mode.
5. **Track failures across all qualifying entries.** Collect every entry whose symbol was not found in any scanned remediation path into an `unresolved[]` list. After processing every qualifying entry, if `unresolved[]` is non-empty: HALT with a consolidated report listing every unresolved entry (`name`, `severity`, `remediation_paths`, `files_scanned`, `exports_found_in_scan`). Template:

   ```
   Targeted re-extraction failed for {N} Critical/High gap(s).

   Critical and High gaps must resolve to AST provenance. The Remediation text for
   the entries below does not name a file that contains the expected export, so the
   workflow cannot produce a non-null `source_file` / `source_line` without
   hallucinating.

   Unresolved entries:
     {for each entry in unresolved[]:}
       - {name} ({severity})
         remediation_paths: {paths}
         files_scanned:     {count}
         exports_matched:   0

   Fix one of the following, then re-run update-skill:
     a) Add a `file:line` citation to the Gap Report `Source:` field.
     b) Edit the Remediation text to name the file(s) that actually contain the export(s).
     c) Downgrade the gap(s) to Medium/Low/Info (accepts the degraded documentation outcome).
   ```

   Exit with status `halted-for-remediation-path`. Step-04 merge has not run; no partial writes.

6. **Success summary** — record `targeted_reextraction: {resolved_count, files_scanned, exports_matched, tier}` in workflow context. The evidence report (step 6 §4) surfaces this alongside the verified / moved / missing tally.

**Why halt instead of degrading to `unknown`:** a Critical or High gap by definition blocks skill usefulness — it is either missing documentation for a public API or a wrong signature. Silently writing `source_file: null` for a blocking gap produces a skill that passes re-test but still hides the broken behavior behind a placeholder. The halt forces the test report to carry usable remediation information — a one-time fix-up that is far cheaper than a downstream audit trying to track why the "repaired" skill still fails.

### 1. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the original brief or metadata:**

"**Docs-only skill detected.** This skill was generated from external documentation, not source code. Re-extraction will re-fetch the original `doc_urls` to check for updated content."

- Re-fetch each URL from `doc_urls` (from the brief or metadata) using whatever web fetching capability is available
- Extract updated API information with T3 `[EXT:{url}]` citations
- Build the updated extraction inventory from fetched content
- Skip all source code extraction below — proceed directly to the merge step (section 5 or equivalent)

**If `source_type: "source"` (default):** Continue with source extraction below.

### 1b. Determine Extraction Strategy by Tier

**Remote Source Resolution (Forge/Deep only):**

**MCP source access (ordered fallback):** When `source_repo` is set in metadata.json, try each MCP tool in order to fetch only the changed files from the change manifest. This avoids clone overhead entirely. Tools are ordered by data freshness — gh API returns live GitHub content and is preferred for update-skill where current file versions are required. zread and deepwiki depend on manual indexing and may return stale data if indexes haven't been refreshed since the changes being extracted.

1. **gh API** — `gh api repos/{owner}/{repo}/contents/{path}` for raw file content
   - If accessible: fetch file content (base64-decoded), always current
   - If rate-limited, 404, or inaccessible: log tool and reason, continue to next tool
2. **zread** — `get_repo_structure` + `read_file` for targeted file access
   - If repo found: fetch changed files, proceed with extraction
   - If "repo not found" or error: log tool and reason, continue to next tool
   - Caveat: indexed data — may be stale if index wasn't refreshed after the target changes
3. **deepwiki** — `ask_question` for targeted export/signature queries
   - If repo indexed and returns usable source data: extract from response
   - If no results or repo not indexed: log tool and reason, continue to next tool
   - Caveat: returns synthesized content, not raw source — extraction quality varies; index may be stale

**Confidence labeling:** MCP-fetched content written to a temp file and analyzed with ast-grep → T1. MCP-fetched content analyzed with pattern matching (AST unavailable) → T1-low.

**If all MCP tools fail for this repo:** Fall back to workspace or ephemeral clone — load and follow `{remoteSourceResolutionData}` for clone setup, version reconciliation, and AST tool unavailability handling.

**If all approaches fail (MCP + workspace/ephemeral clone):** Degrade to provenance-map-only analysis (State 2, T1 confidence from compilation-time data). Warn user: "Source access failed for {source_repo}. Analysis limited to provenance-map baseline."

**Quick tier (text pattern matching):**
- Extract function/class/type names via regex patterns
- Extract export statements via text matching
- Confidence: T1-low (pattern-matched, not AST-verified)

**Forge tier (AST structural extraction):**

⚠️ **CRITICAL:** Load and follow the **AST Extraction Protocol** from `{extractionPatternsData}`. Use the decision tree based on the number of changed files: prefer MCP `find_code()` for small sets, `find_code_by_rule()` with scoped YAML rules for medium sets, and CLI `--json=stream` with line-by-line streaming for large sets. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases.

- Extract: function signatures, type definitions, class members, exported constants
- Extract: parameter types, return types, JSDoc/docstring comments
- Confidence: T1 (AST-verified structural truth)

**Tier degradation handling (Forge/Forge+/Deep):** If ast-grep is unavailable or fails on individual files, follow `{tierDegradationRulesData}` for fallback strategy and user notification requirements. Silent degradation is forbidden — the user must always know when AST extraction was skipped.

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions (T1)
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: T1 for structural, T2 for semantic enrichment

**Tool resolution:** `ast_bridge` → ast-grep MCP tools (`find_code`, `find_code_by_rule`) or `ast-grep` CLI. `qmd_bridge` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Extract Changed Files

**Skip authoritative doc paths.** Before iterating the change manifest, build a skip set from `promoted_docs_new[]` (populated by step 2 §1b) and any existing `file_entries[]` entries with `file_type: "doc"` from the provenance map. These are documentation files tracked for drift detection only — they must not reach AST extraction, which would produce ghost entries on non-code content. If a change manifest entry matches the skip set, skip it silently and continue; doc-type drift is handled by step 2 Category D and step 4 Priority 6/7.

DO NOT BE LAZY — For EACH remaining file in the change manifest with status MODIFIED, ADDED, or RENAMED, launch a subprocess that:

1. Loads the source file
2. Performs tier-appropriate extraction (Quick/Forge/Forge+/Deep)
3. For each export found:
   - Record: export name, type (function/class/type/constant), signature
   - Record: file path, start line, end line
   - Record: parameters with types (if function/method)
   - Record: return type (if function/method)
   - Record: JSDoc/docstring summary (if present)
   - Label: confidence tier (T1/T1-low/T2)
4. Returns structured extraction findings to parent

**For DELETED files:** No extraction needed — deletions handled in merge step.

**For MOVED files:** Re-extract at new location to update file:line references.

**Re-export tracing (Forge/Deep only):** After extracting changed files, check if any public exports from the package entry point (`__init__.py`, `index.ts`, `lib.rs`) are unresolved — particularly when a changed file is part of a module re-export chain. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` to trace unresolved symbols to their actual definition files.

### 2b. CCC Semantic Ranking (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml:**

Before aggregating extraction results, use CCC to assess semantic significance of changes:

1. Run `ccc_bridge.search("{skill_name}", source_root, top_k=15)` — **Tool resolution:** `/ccc` skill search (Claude Code), ccc MCP (Cursor), `ccc search` (CLI) — to get the skill's most semantically central files
2. Cross-reference the change manifest files with CCC results
3. Files appearing in BOTH the change manifest AND CCC's top results are **semantically significant changes** — flag them for priority in the merge step
4. Store `{ccc_significant_changes: [{file, score}]}` in context

This helps the merge step (section 4) prioritize which changes are most likely to affect the skill's core content vs. peripheral modifications.

CCC failures: skip ranking silently, all changes treated equally.

**Note on remote sources:** If `source_root` is a workspace clone, the CCC index may already exist from a prior forge and can be reused via `ccc search --refresh`. If the source is an ephemeral fallback clone, the clone path is not indexed by CCC — the search will return empty results and semantic ranking will be skipped. Deferred CCC indexing is implemented in create-skill step 3 but not in update-skill. All changes are treated equally for ephemeral remote sources.

**IF `tools.ccc` is false:** Skip this section silently.

### 3. Deep Tier QMD Enrichment (Conditional)

**ONLY if forge_tier == Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the skill being updated AND `type` is `"extraction"`.

**If a matching extraction collection is found:**
Launch a subprocess that loads qmd_bridge and for each changed export:
1. Queries the `{skill_name}-extraction` collection for semantic context related to the export
2. Searches for usage patterns, documentation references, temporal history
3. Returns T2 evidence per export (usage frequency, context snippets, related concepts)

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. T2 enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment — extraction still produces T1 results.

**If forge_tier != Deep:** Skip this section with notice: "QMD enrichment skipped (tier: {forge_tier})"

### 4. Compile Extraction Results

Aggregate all subprocess results into structured extraction data:

```
Extraction Results:
  files_extracted: [count]
  exports_extracted: [count]
  confidence_breakdown:
    T1: [count]
    T1-low: [count]
    T2: [count]

  Per-file extractions:
    {file_path}:
      exports:
        - name: {export_name}
          type: function|class|type|constant
          signature: {full signature}
          location: {file}:{start_line}-{end_line}
          confidence: T1|T1-low|T2
          parameters: [{name, type}]
          return_type: {type}
          docstring: {summary}
          qmd_evidence: {if Deep tier}
```

### 5. Display Extraction Summary and Auto-Proceed

"**Re-Extraction Complete:**

| Metric | Count |
|--------|-------|
| Files extracted | {count} |
| Exports extracted | {count} |
| T1 (AST-verified) | {count} |
| T1-low (pattern-matched) | {count} |
| T2 (QMD-enriched) | {count} |

**Proceeding to merge with existing skill...**"

### 6. Present MENU OPTIONS

Display: "**Proceeding to merge...**"

- After extraction results are compiled, immediately load, read entire file, then execute {nextStepFile}
- This is an auto-proceed step with no user choices

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all changed files have been extracted and results compiled will you load {nextStepFile} to begin the merge operation.


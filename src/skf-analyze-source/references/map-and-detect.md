---
nextStepFile: 'recommend.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: '{unitDetectionHeuristicsPath}'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
findCyclesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-cycles.py'
  - '{project-root}/src/shared/scripts/skf-find-cycles.py'
pairIntersectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-pair-intersect.py'
  - '{project-root}/src/shared/scripts/skf-pair-intersect.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Map Exports and Detect Integrations

## STEP GOAL:

To analyze each qualifying unit's export surface and import graph, detect cross-unit integration points, propose composite merges and flag potential stack skill candidates, completing the analysis foundation needed for recommendations.

## Rules

- Delegate per-unit deep analysis to a subagent when available (parallelizes across units; main-thread fallback is fine)
- For each qualifying unit, perform thorough export surface analysis — do not shortcut
- Do not make recommendations (Step 05)

## MANDATORY SEQUENCE

### 1. Load Context

Read {outputFile} to obtain:
- Qualifying units from the Identified Units section: names, paths, scope types, languages, file counts and each unit's own manifest (path, name and ecosystem)
- `forge_tier` from frontmatter

Load {heuristicsFile} for stack skill candidate detection rules.

### 2. Map Export Surfaces Per Unit (Subagent Fan-Out)

For each qualifying unit, delegate deep analysis to a subagent so per-unit work runs in parallel and the parent's context stays clean.

**Resolve `{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}`; first existing path wins. If no candidate exists, HARD HALT with exit code 3 (`resolution-failure`) and the error envelope on stderr (shape in `references/headless-contract.md`). Pass the resolved path to every subagent.

**Subagent fan-out protocol:**

1. **Build the qualifying-unit list.** Read the unit list produced upstream (Step §3 / §4 outputs already in workflow context — names, paths, scope types, languages, file counts). Do not re-scan the project here.

2. **Delegate per-unit deep analysis to a subagent.** For each qualifying unit, launch a subagent task with these explicit constraints:
   - The subagent reads only that unit's directory tree
   - The subagent analyzes exports / usage / CCC signals / scripts+assets for that one unit
   - **The parent does not read the unit's source files before delegating** (avoid the implicit-read trap — the whole point of fan-out is to keep large source bodies out of the parent's context)

3. **Per-unit analysis the subagent performs:**

   **Export surface (every tier):** run the recipe runner on the unit's own folder. For the languages it has ast-grep recipes for (Python, JavaScript and TypeScript, Rust, Go, Vue) it lists the files, runs the recipes, follows the entry points and counts the public API, so the subagent neither greps nor counts those exports by hand:
   ```bash
   uv run {extractPublicApiHelper} --mode full --source-root "{unit_root}" --scope-type {unit_scope_type} --tier {forge_tier}
   ```
   `{unit_root}` is the unit's folder in the analyzed source (its path under the unit's own project path) and `{unit_scope_type}` its scope type from Identified Units.

   **No recipe for the unit's language:** when `files_in_scope` is 0, or `files_without_recipes` lists the extension of the unit's language (Java, Kotlin, Swift, C#, PHP, Ruby and C or C++ have no recipe), the run counted none of its exports, whatever its exit code. Read the public declarations of the unit's source files by eye, as on exit 3: `exports_count`, `api_surface` and `export_pattern` from what you read (for example "public classes: 14, interfaces: 3"), `strategy_used: "source-read"`, `confidence: "T1-low"`.

   Otherwise read the JSON by the exit code:
   - **0 or 1:** `exports_count` ← `counts.exports_public_api`, `api_surface` ← the names in `entry_point_diff.public[]`, `export_pattern` ← `entry_points.status` with `aggregates.by_type` (for example "barrel: 12 functions, 5 classes", marked "capped" when `truncated` is true), `strategy_used: "ast-grep"`, `confidence: "T1"`. Then read by eye what the recipes could not, and name each one in `warnings`: every `entry_point_diff.extraction_gaps[]` name (public, but no recipe found its definition: read it at its `file` and `line`) and every `file_issues[]` file (one the parser could not fully read: add the exports it shows to `api_surface`). Exit 1 (`status: "incomplete"`) means an ast-grep run failed on some files: keep what it returned and put its `errors[]` in `warnings`.
   - **3** (no ast-grep the runner can run): the JSON still lists `entry_points.files`. Read the exports from those entry-point files by eye (from the unit's source files when it lists none), with `strategy_used: "source-read"` and `confidence: "T1-low"`.
   - **2:** an input error, named on stderr (a wrong path or flag): fix the call and run it again.

   **Tier-aware extras:**
   - **Forge+ tier:**
     - If `tools.ccc` is true: run `ccc_bridge.search("{unit_name} exports public API", top_k=15)` to discover semantically relevant files beyond directory scan. Tool resolution: prefer the `/ccc` skill search (Claude Code) or ccc MCP server (Cursor); fall back to the `ccc search` CLI if neither is available; if no ccc tool resolves, skip CCC discovery and record `ccc: unavailable` in per-unit findings.
     - Record CCC signals in per-unit findings: top 3 CCC-ranked file names (or "—" if no ccc results)
   - **Deep tier:**
     - If QMD available: query for temporal evolution of identified exports (deprecation signals, recent additions, refactoring patterns)
     - Record semantic relationships between exports (which exports reference/depend on each other)

   **Subagent must also record:**
   - Script/asset presence: check for `scripts/`, `bin/`, `assets/`, `templates/` directories and files matching detection signals in `{heuristicsFile}`
   - The export-surface call's `strategy_used`, `confidence` and `warnings`

4. **Subagent return contract.** Each subagent returns only this JSON object — no prose, no commentary, no markdown fences:

   ```json
   {
     "unit_name": "...",
     "files_count": N,
     "exports_count": N,
     "export_pattern": "...",
     "api_surface": ["..."],
     "scripts_assets": {"scripts": [], "assets": []},
     "ccc_signals": {"top_files": [], "available": <bool>},
     "strategy_used": "ast-grep|source-read",
     "confidence": "T1|T1-low",
     "warnings": []
   }
   ```

   `files_count` is the unit's file count from Identified Units, not the runner's `files_in_scope`, which leaves out every file no recipe reads.

5. **Parent post-processing.** Strip any wrapping markdown fences (subagents sometimes wrap JSON in ` ```json … ``` ` despite the contract) before parsing. Validate each payload against the contract; if a key is missing, log a warning to `workflow_warnings[]` and continue with that unit's degraded record. Add each record's `warnings` to `workflow_warnings[]`.

6. **Aggregate.** Collect all per-unit JSON payloads into `per_unit_findings[]` in workflow context for use by §3 (import graph), §4 (integration points), §5 (composites and stack candidates), §6 (findings presentation), and downstream stages (recommend.md, generate-briefs.md).

**Per-unit export summary (built from `per_unit_findings[]`):**

| Unit | Files | Exports | Export Pattern | API Surface | Scripts/Assets | CCC Signals |
|------|-------|---------|----------------|-------------|----------------|-------------|
| {name} | {count} | {count} | {pattern} | {small/medium/large} | {N scripts, M assets or --} | {CCC signals or --} |

**Graceful degradation.** If subagents are unavailable in the current runtime, the parent performs the per-unit analysis sequentially in the main thread with the same export-surface call and tier-aware extras. Each main-thread analysis still produces the same JSON record shape so downstream stages remain agnostic to the execution mode.

### 3. Map Import Graph

Which unit imports which, how many files import each unit, which units are imported together and which import each other in a cycle each have one right answer per tree, so the helpers compute them and this section reads their output.

**Resolve `{scanManifestsHelper}`, `{countImportsHelper}`, `{findCyclesHelper}` and `{pairIntersectHelper}`** from their probe orders; first existing path wins for each. If one has no candidate, HARD HALT with exit code 3 (`resolution-failure`) and the error envelope on stderr (shape in `references/headless-contract.md`).

**Units JSON.** One entry per qualifying unit, from its Identified Units row: `{"name": "<unit name>", "path": "<its path, relative to the source root>", "manifest_name": "<its own manifest's name>", "ecosystem": "<its own manifest's ecosystem>"}`, with `manifest_name` and `ecosystem` left out for a unit without a manifest. The import helper works out the names other code imports each unit by from what the unit declares. Add `"modules"` only for a folder without a manifest that code imports by name: a Python package folder (`["acme"]`) or a Go package inside a module (`["example.com/svc/internal/auth"]`).

Run this once for each entry of `project_paths[]` (`{source_root}` below), over the units under it:

```bash
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cat > "$work/units.json" <<'SKF_UNITS'
{"units": [<one entry per qualifying unit under {source_root}>]}
SKF_UNITS
uv run {scanManifestsHelper} scan "{source_root}" > "$work/manifests.json"
uv run {countImportsHelper} count "{source_root}" --units "$work/units.json" --deps "$work/manifests.json" > "$work/imports.json"
cat "$work/imports.json" "$work/manifests.json"
uv run {findCyclesHelper} find --edges "$work/imports.json"
uv run {countImportsHelper} count "{source_root}" --units "$work/units.json" --format libraries > "$work/importers.json"
uv run {pairIntersectHelper} intersect --libraries "$work/importers.json"
```

A helper that exits non-zero names the problem on stderr (a unit name or path given twice, a malformed entry): fix the units JSON and run the block again.

Read the output:

- **Imports From / Imported By:** each `units[]` entry's `imports_from` and `imported_by`. Its `file_count` is the number of import sites (files outside the unit that import it), and `files` lists them with the line of their first import.
- **External Deps:** each `units[]` entry's `external_deps`, the manifest dependencies its files import.
- **Mutual dependencies:** each `cycles[]` entry (`["a", "b", "a"]` is two units that import each other).
- **Co-imported units:** each `pairs[]` entry: `intersection_count` files import both units, listed in `files`. When `truncated` is true, run that last call again with `--top-k` set to its `total_pairs`, so no pair is left out.
- Keep the scan output (`manifests.json`) for §5, whose cohesion triggers read its `umbrella_candidates[]` and each member's `name`, `private` and `internal_deps`.

**Build cross-reference matrix:**

| Unit | Imports From | Imported By | Import Sites | External Deps |
|------|-------------|-------------|--------------|---------------|
| {name} | {imports_from} | {imported_by} | {file_count} | {external_deps count, or --} |

### 4. Detect Integration Points

Identify cross-unit integration patterns:

**Direct integrations:**
- Each §3 `edge_files[]` entry (unit `from` imports from unit `to`, through the `files` it lists with the line of their first import) → document the interface boundary
- Shared type definitions across units
- Cross-unit function calls

**For each integration point document:**
- Source unit → Target unit
- Integration type (import, shared types, API call, message passing, shared state)
- Files involved (with paths)
- Coupling strength (tight / loose / indirect)

### 5. Decide Composites and Stack Skill Candidates

Decide both here, in one pass over §3's graph and §4's integration map, so each group of units is judged once: a **composite** when its units only deliver value together, a **stack skill candidate** when each is useful on its own and they are also used together. A group is never both.

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If no candidate exists, HARD HALT with exit code 3 (`resolution-failure`) and the error envelope on stderr (shape in `references/headless-contract.md`).

1. **Composite merge proposals.** Apply the Composite Boundary triggers in {heuristicsFile} (mutual hard dependency, shared integration surface, and the Cohesion Triggers: umbrella facade, shared runtime contract, internal building blocks) to the qualifying units. The evidence comes from the helpers: `cycles[]` for a mutual dependency, `edges[]` and §4's shared types for a shared integration surface, and the §3 scan's `umbrella_candidates[]` and each member's `internal_deps` and `private` for the cohesion triggers. For each group that meets a trigger, propose one composite:
   - **Constituents:** the unit names and paths merged
   - **Heuristic and evidence:** the trigger and what showed it (the cycle, the umbrella candidate and the members its `internal_deps` cover, the `private` flags, the shared types and their files)
   - **Name:** name every proposal in one call to the helper that names every unit and brief ({heuristicsFile}'s Unit Names), one entry each: `target` is its constituents' project path, `manifest_name` the facade's manifest name when an umbrella facade triggered the merge (else null), and `members` the constituents' manifest names:
     ```bash
     uv run {skillInventoryHelper} derive-name --from - <<'SKF_COMPOSITE_NAMES'
     [{"target": "<project path>", "manifest_name": "<facade name or null>", "members": ["<constituent manifest name>", ...]}, ...]
     SKF_COMPOSITE_NAMES
     ```
     Each `names[].name` is that proposal's name; give the entries `unnamed` and `duplicates` list a name of your own, from their constituents.
2. **Stack skill candidates.** Check the four stack-skill indicators defined in {heuristicsFile}'s Stack Skill Candidate Detection section against the units no composite proposal groups: co-import frequency is a §3 `pairs[]` entry with an `intersection_count` of 3 or more, and integration adapter, shared state and orchestration layer come from §4. When the user rejects a composite in §6, check its constituents here too.

**For each stack skill candidate, document:**
- Units involved
- Detection signal
- Recommended stack skill grouping
- Evidence (specific files/lines)

### 6. Present Findings

"**Export Mapping and Integration Detection Complete**

**Export Map Summary:**
{Per-unit export summary table}

**Cross-Reference Matrix:**
{Import graph matrix}

**Integration Points:** {count}
{List each integration with source → target, type, coupling}

**Composite Merge Proposals:** {count}

| # | Composite Name | Constituents | Heuristic | Evidence |
|---|----------------|--------------|-----------|----------|
| 1 | {name} | {constituent unit names and paths} | {mutual hard dependency / shared integration surface / umbrella facade / shared runtime contract / internal building blocks} | {evidence} |

**Stack Skill Candidates:** {count}
{List each candidate with units involved and detection signal}

**Observations:**
- {Key architectural patterns observed}
- {Tightly coupled areas}
- {Loosely coupled areas ideal for independent skills}

Does this analysis look complete? Any integration patterns I should investigate further? Accept or reject each composite merge proposal."

Wait for user feedback. Adjust analysis based on user input. An approved composite replaces its constituents as one unit: `Boundary Type: Composite`, its constituents' paths as its Path, the scope type and language of its dominant constituent (the one with the most exports), and confidence from the strength of its trigger. A rejected one leaves its constituents as separate units.

**GATE [default: accept]:** if `{headless_mode}`, accept every composite merge proposal and log: "headless: auto-accept {count} composite merges".

### 7. Append to Report

Append the complete "## Export Map" section to {outputFile}:
Replace `[Appended by map-and-detect]` under Export Map with:
- Per-unit export summary table
- Export pattern analysis

Append the complete "## Integration Points" section to {outputFile}:
Replace `[Appended by map-and-detect]` under Integration Points with:
- Cross-reference matrix
- Integration point details
- Composite merge proposals and decisions: name, constituents with their paths, heuristic, evidence
- Stack skill candidate flags

In the Identified Units classification table, replace the constituent rows of each approved composite with the composite's one row (its Path the constituents' paths), so recommend builds one card for it.

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'map-and-detect' to existing array]
lastStep: 'map-and-detect'
confirmed_composites: [{list of approved composites: {name, constituents: [{name, path}], heuristic}}]
stack_skill_candidates: [{list flagged candidate groupings}]
```

(`confirmed_composites` is an empty array when no composite was proposed or all were rejected. generate-briefs puts every constituent's path in the composite brief's `scope.include`.)

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Recommendations | [D] Discover Additional Source"

#### Menu Handling Logic:

- IF C: Save findings to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF D: Accept a new repo path/URL from the user. Run a lightweight scan (directory structure + manifest detection from step 02) and classify (unit identification from step 03) for the new source only. Merge results into the existing report — append new units to the unit list, update `project_paths[]` in frontmatter. Then redisplay this step's export mapping for the new units before returning to the menu.
- IF Any other: help user, then [Redisplay Menu Options](#8-present-menu-options)

**GATE [default: C]** — present the menu and wait for the user's choice. If `{headless_mode}`: auto-proceed with [C] Continue past export/integration findings, log: "headless: auto-continue past integration analysis".


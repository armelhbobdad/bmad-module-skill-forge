---
nextStepFile: 'recommend.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
discoverFile: 'references/discover-additional-source.md'
unitExportsFile: 'references/map-unit-exports.md'
scanRootFile: 'references/scan-root.md'
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
checkUnitRecordsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-unit-records.py'
  - '{project-root}/src/shared/scripts/skf-check-unit-records.py'
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

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Context

Read {outputFile} to obtain:
- Qualifying units from the Identified Units section: names, project paths, paths, scope types, languages, file counts, statuses and each unit's own manifest (path, name and ecosystem). A unit whose status is `deferred` (outside the goal the user stated) stays in the report and is not analyzed here
- `forge_tier`, `scan_roots` (each project path's scan root) and `refs` from frontmatter

**A scan root that is gone.** A session that resumed this report runs in a new run folder, and the folder of the session that made a copy may be gone. When a recorded scan root no longer exists, make it again by {scanRootFile} into this run's `{run_dir}/source-{i}` and update `scan_roots` in {outputFile}'s frontmatter. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `map-and-detect:1`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

Load {heuristicsFile} for stack skill candidate detection rules.

### 2. Map Export Surfaces Per Unit (Subagent Fan-Out)

For each qualifying unit, delegate deep analysis to a subagent so per-unit work runs in parallel and the parent's context stays clean.

**Resolve `{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}` and **`{checkUnitRecordsHelper}`** from `{checkUnitRecordsProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `map-and-detect:2`): "`{the missing script}` is missing. Re-install SKF."

**Subagent fan-out protocol:**

1. **Build the qualifying-unit list.** Read the unit list produced upstream (names, project paths, paths, scope types, languages, file counts), leaving out the deferred units. Do not re-scan the project here.

2. **Map each unit's exports.** Load, read the entire file, then execute {unitExportsFile} for the qualifying units: it delegates each one to a subagent with `{unit_root}` its path under the scan root of its project path and its file count from Identified Units, has the subagent write the unit's record to `{run_dir}/unit-records/{unit_name}.json`, checks the records and returns them.

3. **Aggregate.** Collect the checked `records` into `per_unit_findings[]` in workflow context for use by §3 (import graph), §4 (integration points), §5 (composites and stack candidates), §6 (findings presentation), and downstream stages (recommend.md, generate-briefs.md).

**Per-unit export summary (built from `per_unit_findings[]`):**

| Unit | Files | Exports | Export Pattern | API Surface | CCC Signals |
|------|-------|---------|----------------|-------------|-------------|
| {name} | {count} | {count} | {pattern} | {small/medium/large} | {CCC signals or --} |

### 3. Map Import Graph

Which unit imports which, how many files import each unit, which units are imported together and which import each other in a cycle each have one right answer per tree, so the helpers compute them and this section reads their output.

**Resolve `{scanManifestsHelper}`, `{countImportsHelper}`, `{findCyclesHelper}` and `{pairIntersectHelper}`** from their probe orders; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `map-and-detect:3`): "`{the missing script}` is missing. Re-install SKF."

**Units JSON.** One entry per qualifying unit, from its Identified Units row: `{"name": "<unit name>", "path": "<its path, relative to the source root>", "manifest_name": "<its own manifest's name>", "ecosystem": "<its own manifest's ecosystem>"}`, with `manifest_name` and `ecosystem` left out for a unit without a manifest. The import helper works out the names other code imports each unit by from what the unit declares. Add `"modules"` only for a folder without a manifest that code imports by name: a Python package folder (`["acme"]`) or a Go package inside a module (`["example.com/svc/internal/auth"]`).

Run this once per project path, the `{i}`-th entry of `project_paths[]`, with `{source_root}` its scan root, over the units under it. `{run_dir}/manifests-{i}.json` is the manifest scan scan-project wrote; when it is missing, as in a session that resumed the report, run `uv run {scanManifestsHelper} scan "{source_root}" > "{run_dir}/manifests-{i}.json"` first.

```bash
cat > "{run_dir}/units-{i}.json" <<'SKF_UNITS'
{"units": [<one entry per qualifying unit under {source_root}>]}
SKF_UNITS
uv run {countImportsHelper} count "{source_root}" --units "{run_dir}/units-{i}.json" --deps "{run_dir}/manifests-{i}.json" > "{run_dir}/imports-{i}.json"
uv run {countImportsHelper} summary "{run_dir}/imports-{i}.json" --manifests "{run_dir}/manifests-{i}.json"
uv run {findCyclesHelper} find --edges "{run_dir}/imports-{i}.json"
uv run {countImportsHelper} count "{source_root}" --units "{run_dir}/units-{i}.json" --format libraries > "{run_dir}/importers-{i}.json"
uv run {pairIntersectHelper} intersect --libraries "{run_dir}/importers-{i}.json"
```

A helper that exits non-zero names the problem on stderr (a unit name or path given twice, a malformed entry): fix the units JSON and run the block again.

Read the output. The `summary` line prints the graph without the file lists, which stay in `{run_dir}/imports-{i}.json`:

- **Imports From / Imported By:** each summary `units[]` entry's `imports_from` and `imported_by`. Its `file_count` is the number of import sites (files outside the unit that import it).
- **External Deps:** each summary `units[]` entry's `external_dep_count`, the number of manifest dependencies its files import.
- **Mutual dependencies:** each `cycles[]` entry (`["a", "b", "a"]` is two units that import each other).
- **Co-imported units:** each `pairs[]` entry: `intersection_count` files import both units, listed in `files`. When `truncated` is true, run that last call again with `--top-k` set to its `total_pairs`, so no pair is left out.
- **Cohesion evidence:** the summary's `umbrella_candidates[]` and `manifests[]` (each manifest's `name`, `private` and `internal_deps`), which §5 reads.

**Build cross-reference matrix:**

| Unit | Imports From | Imported By | Import Sites | External Deps |
|------|-------------|-------------|--------------|---------------|
| {name} | {imports_from} | {imported_by} | {file_count} | {external_dep_count, or --} |

### 4. Detect Integration Points

Identify cross-unit integration patterns:

**Direct integrations:**
- Each §3 summary `edge_files[]` entry (unit `from` imports from unit `to` in `file_count` files, the first of them listed in `files` with the line of their first import) → document the interface boundary. When the boundary needs every file, read that entry in `{run_dir}/imports-{i}.json`
- Shared type definitions across units
- Cross-unit function calls

**For each integration point document:**
- Source unit → Target unit
- Integration type (import, shared types, API call, message passing, shared state)
- Files involved (with paths)
- Coupling strength (tight / loose / indirect)

### 5. Decide Composites and Stack Skill Candidates

Decide both here, in one pass over §3's graph and §4's integration map, so each group of units is judged once: a **composite** when its units only deliver value together, a **stack skill candidate** when each is useful on its own and they are also used together. A group is never both.

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If no candidate exists, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `map-and-detect:5`): "`skf-skill-inventory.py` is missing. Re-install SKF."

1. **Composite merge proposals.** Apply the Composite Boundary triggers in {heuristicsFile} (mutual hard dependency, shared integration surface, and the Cohesion Triggers: umbrella facade, shared runtime contract, internal building blocks) to the qualifying units. The evidence comes from the helpers: `cycles[]` for a mutual dependency, `edge_files[]` and §4's shared types for a shared integration surface, and the §3 summary's `umbrella_candidates[]` and each manifest's `internal_deps` and `private` for the cohesion triggers. For each group that meets a trigger, propose one composite:
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

### 6. Present the Findings and Confirm

Show the user the per-unit export summary, the cross-reference matrix, each integration point (source to target, type, coupling), the composite merge proposals, the stack skill candidates (units involved and detection signal), and the observations (key architectural patterns, tightly and loosely coupled areas). Present the proposals as a table:

| # | Composite Name | Constituents | Heuristic | Evidence |
|---|----------------|--------------|-----------|----------|
| 1 | {name} | {constituent unit names and paths} | {mutual hard dependency / shared integration surface / umbrella facade / shared runtime contract / internal building blocks} | {evidence} |

Then display:

"Accept or reject each composite merge proposal (every one is accepted unless you reject it), or name an integration pattern to investigate further. **Select:** [C] Continue to Recommendations | [D] Discover Additional Source | [X] Cancel and exit"

An approved composite replaces its constituents as one unit: `Boundary Type: Composite`, its constituents' paths as its Path, the project path they share, the scope type and language of its dominant constituent (the one with the most exports), and confidence from the strength of its trigger. A rejected one leaves its constituents as separate units.

#### Menu Handling Logic:

- IF C: go to §7
- IF D: load, read the entire file, then execute {discoverFile} with the project path the user gives. It adds the new path's units to Identified Units and returns their export records, import graph, composite proposals and stack skill candidates, which join the findings here, so §7 writes the Export Map and Integration Points with them: redisplay §6 with them included.
- IF X: HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `map-and-detect:6`): "Cancelled at the export mapping."
- IF Any other: apply the composite decisions, investigate what the user named, show what changed, then [Redisplay Menu Options](#6-present-the-findings-and-confirm)

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: accept every composite merge proposal and continue with [C], and record that decision the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "map-and-detect.findings", "default_action": "C", "taken_action": "C", "reason": "headless: auto-accept {count} composite merges and continue past the integration analysis", "evidence": {"composites": [<the name of each accepted composite>], "stack_skill_candidates": <the candidate count>}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost.

### 7. Append to Report and Continue

Replace `[Appended by map-and-detect]` under Export Map in {outputFile} with:
- Per-unit export summary table
- Export pattern analysis

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

Then load, read the entire file, then execute {nextStepFile}.

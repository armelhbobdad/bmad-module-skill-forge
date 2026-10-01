---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
scanRootFile: 'references/scan-root.md'
unitExportsFile: 'references/map-unit-exports.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
disqualifyCandidatesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-disqualify-candidates.py'
  - '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
checkUnitRecordsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-unit-records.py'
  - '{project-root}/src/shared/scripts/skf-check-unit-records.py'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
findCyclesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-cycles.py'
  - '{project-root}/src/shared/scripts/skf-find-cycles.py'
pairIntersectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-pair-intersect.py'
  - '{project-root}/src/shared/scripts/skf-pair-intersect.py'
---

<!-- Config: communicate in {communication_language}. -->

# Discover Additional Source

## STEP GOAL:

To add one more project path to a running analysis: scan it, classify and name its units, map their exports and imports, propose its composite merges, and merge all of it into the report, then return to the menu that loaded this file (the [D] option of map-and-detect and of recommend), which says what to do with the new units.

## Rules

- Interactive only: a headless run never takes [D], since both menus default to [C]
- Work on the new path only: the units already in the report keep their classification, records and decisions
- Every helper below reads the new path's scan root, never `{project-root}` (the forge workspace)

## MANDATORY SEQUENCE

Every HARD HALT in this file names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Resolve every helper first**, each from its probe order in the frontmatter (first existing path wins): `{scanManifestsHelper}`, `{disqualifyCandidatesHelper}`, `{skillInventoryHelper}`, `{detectLanguageHelper}`, `{extractPublicApiHelper}`, `{checkUnitRecordsHelper}`, `{countImportsHelper}`, `{findCyclesHelper}` and `{pairIntersectHelper}`. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `discover-additional-source:0`): "`{the missing script}` is missing. Re-install SKF."

### 1. Take the New Path

Take the path the user gave with [D], or ask for one: "**Which repository or folder should I add?** A local path or a URL." Check that it exists (local) or is accessible (remote); otherwise say so and ask again. Read {outputFile}'s frontmatter (`project_paths`, `scan_roots`, `refs`, `target_ref`, `forge_tier`, `intent_hint`, `existing_skills`, `existing_briefs`). The new path is entry `{i}` of `project_paths[]` (its current length plus one). It takes `target_ref` as its ref when the report sets one (no `--target-refs` entry can name it), else none. Load {heuristicsFile}.

### 2. Scan It

Make its **scan root** by {scanRootFile}, with the ref §1 gave it. If a command there fails, show its first stderr line and ask for another path (§1). Then list its manifests:

```bash
uv run {scanManifestsHelper} scan "{scan_root}" > "{run_dir}/discover-{i}-manifests.json"
```

The candidate boundaries are its `folders[]` entries (`.` is the root), plus any folder that holds a Docker or compose file of its own, judged as scan-project judges a boundary: leave out a folder whose manifest only gathers the member folders below it (a workspace root such as a private `package.json` that lists `workspaces`, or a Cargo virtual workspace) with no code of its own. `.` stays a candidate only when it holds code of its own outside the other candidates, or no other candidate is left. Name a candidate by its folder.

### 3. Classify and Name the New Units

List each candidate's files and apply the deterministic disqualification rules in one call, one entry per candidate with its path relative to the scan root:

```bash
uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root "{scan_root}" --tree-dir "{run_dir}/unit-trees/{i}" <<'SKF_BOUNDARIES'
[{"name": "<candidate folder name>", "path": "<candidate path>"}, ...]
SKF_BOUNDARIES
```

Each record of `kept[]` and `dropped[]` gives the evidence {heuristicsFile}'s Disqualification Rules judge: `files_count`, `loc_total`, `generated_files`, `generated_ratio`, `passes_with_generated`, `manifest`, `signals` and `tree_file` (the candidate's file list). Then judge what the script cannot: drop a mixed candidate only when its own code is no more than glue around its generated files; restore a candidate dropped over files you judge its own code when `passes_with_generated` is true; drop pure configuration and test-only candidates. Name every kept one in one call, by {heuristicsFile}'s Unit Names (`target` is its path, or the new project path itself for a candidate at the root):

```bash
uv run {skillInventoryHelper} derive-name --from - <<'SKF_UNIT_NAMES'
[{"target": "<candidate path>", "manifest_name": <manifest.name>, "private": <manifest.private>}, ...]
SKF_UNIT_NAMES
```

Give the entries `unnamed` and `duplicates` list a name of your own, from their folder, and never a name a unit of the report already has. A unit whose name is in `existing_skills` is already skilled: drop it (recommend update-skill); one in `existing_briefs` keeps the status `briefed`. Classify each unit's boundary type and scope type by {heuristicsFile}'s Boundary Classification, and detect its language from its file list:

```bash
uv run {detectLanguageHelper} --tree-file "{the unit's tree_file}"
```

When `detected_languages` has more than one entry, choose the language the unit documents from its own manifest, or `.source_language` without one. When `intent_hint` is not empty, mark a unit the stated goal clearly leaves out `deferred`, as the report's other deferred units are: it is listed and not analyzed, and the user can restore it.

### 4. Map the New Units

Load, read the entire file, then execute {unitExportsFile} for the new units that are not deferred, each with `{unit_root}` its path under the new scan root and its file count the `files_count` of its §3 record. It writes each unit's record to `{run_dir}/unit-records/{unit_name}.json`, checks the records, records their problems and warnings, and returns them.

**Import graph.** Write the units JSON for the new units, one entry each: `{"name": "<unit name>", "path": "<its path, relative to the scan root>", "manifest_name": "<its own manifest's name>", "ecosystem": "<its own manifest's ecosystem>"}` (no `manifest_name` or `ecosystem` without a manifest; `"modules"` only for a folder without a manifest that code imports by name), then:

```bash
cat > "{run_dir}/discover-{i}-units.json" <<'SKF_UNITS'
{"units": [<one entry per new unit that is not deferred>]}
SKF_UNITS
uv run {countImportsHelper} count "{scan_root}" --units "{run_dir}/discover-{i}-units.json" --deps "{run_dir}/discover-{i}-manifests.json" > "{run_dir}/discover-{i}-imports.json"
uv run {findCyclesHelper} find --edges "{run_dir}/discover-{i}-imports.json"
uv run {countImportsHelper} count "{scan_root}" --units "{run_dir}/discover-{i}-units.json" --format libraries > "{run_dir}/discover-{i}-importers.json"
uv run {pairIntersectHelper} intersect --libraries "{run_dir}/discover-{i}-importers.json"
```

Read each `units[]` entry's `imports_from`, `imported_by`, `file_count` and `external_deps` from the imports file, each `cycles[]` entry (units that import each other) and each `pairs[]` entry (units imported together in `intersection_count` files; when `truncated` is true, run the last call again with `--top-k` set to its `total_pairs`). A helper that exits non-zero names the problem on stderr: fix the units JSON and run the block again.

### 5. Propose Composites and Stack Skill Candidates

Judge the new units as one pass, so a group is never both a composite and a stack skill candidate. Apply the Composite Boundary triggers and the Cohesion Triggers of {heuristicsFile}: a mutual hard dependency from `cycles[]`, a shared integration surface from the imports, and the cohesion triggers from the manifests file's `umbrella_candidates[]` and each member's `name`, `private` and `internal_deps`. Name every proposal in one call (`target` is the new project path, `manifest_name` the facade's manifest name when an umbrella facade triggered it, else null, and `members` the constituents' manifest names):

```bash
uv run {skillInventoryHelper} derive-name --from - <<'SKF_COMPOSITE_NAMES'
[{"target": "<project path>", "manifest_name": "<facade name or null>", "members": ["<constituent manifest name>", ...]}, ...]
SKF_COMPOSITE_NAMES
```

Check the four indicators of {heuristicsFile}'s Stack Skill Candidate Detection against the new units no proposal groups (co-import frequency is a `pairs[]` entry with an `intersection_count` of 3 or more).

### 6. Merge Into the Report and Return

Add to {outputFile}: the new units, with their project path, to the Identified Units classification table (deferred units included), and the dropped candidates to its Disqualification table. Then:

- **Loaded by map-and-detect:** write nothing more. Its Export Map and Integration Points still hold their placeholders, and its §7 writes both sections from the findings these units join.
- **Loaded by recommend:** both sections are already written: add the new units' export rows to the Export Map, and their imports, composite proposals and stack skill candidates to Integration Points.

Update its frontmatter:

```yaml
project_paths: [append the new path]
scan_roots: {add the new path: its scan root}
refs: {add the new path: its ref, when §1 gave it one}
```

Return to the menu that loaded this file with the new units, their records, their import graph, their composite proposals and their stack skill candidates: it presents them and takes the user's decisions.

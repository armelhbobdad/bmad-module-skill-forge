---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
unitsFile: '{forge_data_folder}/analyze-source-units-{project_name}.json'
heuristicsFile: 'references/unit-detection-heuristics.md'
scanRootFile: 'references/scan-root.md'
disqualifyCandidatesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-disqualify-candidates.py'
  - '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
detectRegistryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'
  - '{project-root}/src/shared/scripts/skf-detect-registry.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Identify Units

## STEP GOAL:

To classify each detected boundary from the project scan into discrete skillable units by applying detection heuristics, assigning boundary types and scope types, filtering out disqualified candidates and, in an interactive run with a stated goal, deferring the units outside it before export mapping.

## Rules

- Focus only on unit classification — do not map exports or integration points yet
- Do not generate skill-brief.yaml in this step
- Every classification must cite the detection signals that justify it

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Context

Read {outputFile} to obtain:
- Project Scan results (detected boundaries, manifests, service configurations), grouped by project path
- `project_paths`, `scan_roots` (each project path's scan root: the folder every helper of this step reads), `refs`, `forge_tier`, `intent_hint`, `existing_skills` and `existing_briefs` from frontmatter

**A scan root that is gone.** A session that resumed this report without its earlier run folder works in a new one, without the copies that folder held. When a recorded scan root no longer exists, make it again by {scanRootFile} into this run's `{run_dir}/source-{i}` and update `scan_roots` in {outputFile}'s frontmatter. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `identify-units:1`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

Load {heuristicsFile} for classification rules.

### 2. Apply Detection Heuristics

**Resolve `{disqualifyCandidatesHelper}`** from `{disqualifyCandidatesProbeOrder}`, **`{skillInventoryHelper}`** from `{skillInventoryProbeOrder}` and **`{detectRegistryHelper}`** from `{detectRegistryProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `identify-units:2`): "`{the missing script}` is missing. Re-install SKF."

For each detected boundary from the scan, apply the classification rules from {heuristicsFile} (loaded in §1):

**Step A: Run the disqualification helper (script).** In one call per project path it lists each boundary's files itself, applies the deterministic subset of the rules from {heuristicsFile} (file count, LoC, generated files) and looks up the signal files and the boundary's own manifest. Its output is evidence that Step B judges, not a verdict.

Run it once per project path, the `{i}`-th entry of `project_paths[]` (`{project_path}`), over the boundaries found under it, with `{scan_root}` that path's scan root (never `{project-root}`, the forge workspace) and one entry per boundary, its path relative to the scan root (`.` for a boundary at the root), with forward slashes:

```bash
uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root "{scan_root}" --tree-dir "{run_dir}/unit-trees/{i}" --project-path "{project_path}" > "{run_dir}/filter-{i}.json" <<'SKF_BOUNDARIES'
[{"name": "<boundary folder name>", "path": "<boundary path>"}, ...]
SKF_BOUNDARIES
```

The script lists every boundary's files (what git lists under its path, so ignored build output and installed dependencies stay out), writes each list to the run folder and writes one record per boundary to `{run_dir}/filter-{i}.json`. Each `kept[]` and `dropped[]` record gives `files_count` and `loc_total` (the boundary's own source files, counted as {heuristicsFile}'s Disqualification Rules say), `generated_files` and `generated_ratio` (the files Step B weighs), `passes_with_generated` (whether the size rules pass with those files counted too), `manifest` (the boundary's own manifest, null without one), `signals` (Step D) and `tree_file` (the boundary's file list, from which §3's call detects its language), and a `dropped[]` record also the script's `reason` and its `context`. A boundary path that is no folder under the scan root makes the script exit 1 and name it on stderr: correct that entry and run the call again. Read the file: its `kept[]` is the candidate pool for the classification that follows, and its `dropped[]` holds the script's drops.

**Step B: Judge what the script cannot.**

- **Mixed cases** (`stats.mixed` counts them): a kept boundary whose `generated_files` is not empty. Read the flagged paths and their `match`. Build output or a vendored copy beside the unit's own code leaves the unit standing, and its counts already leave those files out. Drop a mixed boundary only when its own code is no more than glue around the generated files, with reason `generated-code` and one line on why.
- **A drop the flagged files caused:** a boundary dropped as `generated-code`, `auto-generated-tag`, `too-few-files` or `too-low-loc` whose `generated_files` you judge to be its own code (a source folder named `build/` or `dist/`, a header its own tooling writes into code it maintains) goes back into `kept[]` when its `passes_with_generated` is true, with those files named in the notes. When it is false, the boundary stays dropped: even with those files it is too small.
- **The rules the script does not check:** {heuristicsFile}'s Disqualification Rules 3 and 4. Drop a kept boundary that fails one, with reason `pure-configuration` or `test-only`.

Each drop and each restore here is a judgment §3 records, and §6 shows it with its reason and evidence, so the user can override it; a headless run keeps the judgment made here.

**Step C: Name each unit (script), then check it is not already skilled.** The helper that names every brief names the units too, so a unit's name here is the name its brief gets.

1. Name every unit in one call, by {heuristicsFile}'s Unit Names, one entry per kept boundary straight from its record: `target` is its `path` (its project path itself for a boundary at the root), and `manifest_name` and `private` are its `manifest.name` and `manifest.private` (null when `manifest` is null):
   ```bash
   uv run {skillInventoryHelper} derive-name --from - > "{run_dir}/unit-names.json" <<'SKF_UNIT_NAMES'
   [{"target": "<boundary path>", "manifest_name": <manifest.name>, "private": <manifest.private>}, ...]
   SKF_UNIT_NAMES
   ```
   Each `names[].name` in `{run_dir}/unit-names.json` is that unit's name from here on, which §3's call reads. Boundaries whose names would clash are already told apart by their parent folders (`clash` keeps the name they shared); give the entries `unnamed` and `duplicates` list a name of your own, from their folder, in the unit's judgment `name` (§3).
2. **Already skilled:** a unit whose name is in `existing_skills` (a compiled skill) fails {heuristicsFile}'s Disqualification Rule 6: drop it with reason `already-skilled` (recommend `update-skill` instead). A unit whose name is in `existing_briefs` only has a brief from an earlier analysis: it stays a candidate with status `briefed` and its brief's path, and generate-briefs rewrites that brief only if the unit is confirmed.

**Step D: Tally detection signals** per the Detection Signals tables in {heuristicsFile}: cite the file each record's `signals` entry names (and `large_directory`), and judge the signals the helper does not report, as that file says.

**Step E: Classify boundary type** per its Boundary Classification section, and **assign the scope type** from that same section for the boundary's type. This pass classifies each boundary on its own: composite merges are proposed in map-and-detect, once the import graph exists. A component library's demo files and registry are counted and scored, not judged by eye: for each kept unit, run both on its record's `tree_file` (its paths are under the scan root):

```bash
uv run {detectRegistryHelper} demo --files-from "{the unit's tree_file}"
uv run {detectRegistryHelper} registry --files-from "{the unit's tree_file}" --source-root "{scan_root}"
```

Cite in the Signals column `demo {excluded}/{files_listed}` (the demo output's counts) and each `candidates[]` entry whose `qualifies` is true, with its `path` and `score`: {heuristicsFile}'s Component Library Boundary names the test each answers.

### 3. Build Unit Classification Table

Write §2's judgments to `{run_dir}/unit-judgments.json`, a JSON array with one entry per `kept[]` record of every project path, and one per `dropped[]` record you restore or drop with evidence of your own (a script drop without one stays dropped with the script's reason and `context`): `{"project_path": "<its project path>", "path": "<its record's path>", "status": "<new|briefed|deferred|dropped>", "boundary_type": "<Step E>", "scope_type": "<Step E>", "confidence": "<high|medium|low>", "rationale": "<the Signals cell>"}`. A kept status (`new`, `briefed`, `deferred`) needs `boundary_type`, `scope_type`, `confidence` and `rationale`, the Signals cell Step E describes (signal counts as strong/moderate/weak, `demo {excluded}/{files_listed}`, each qualifying registry candidate with its score); `dropped` needs `reason` and `rationale`, its evidence. Add `"name"` for a unit Step C left to you, and `"language"` for a language §4 chose. Then merge them with the filter records and the names, one `--filter` per project path:

```bash
uv run {disqualifyCandidatesHelper} units --filter "{run_dir}/filter-{i}.json" --names "{run_dir}/unit-names.json" --judgments "{run_dir}/unit-judgments.json" --out "{unitsFile}"
```

It names each unit from `unit-names.json`, detects its language and takes its scope patterns from its `tree_file` (§4), writes {unitsFile} and prints three tables: Identified units (the classification table, deferred units included), Language and scope, and Disqualified. §6 shows them and §7 writes them as printed: no row is typed. A kept record without a judgment, a judgment that names no record, a record judged twice, a missing field, a unit without a name or a name two units share makes it exit 1, write nothing and name each project path and path on stderr: correct the judgments and run it again.

### 4. Detect Primary Language Per Unit

§3's call detects each unit's primary language with `skf-detect-language.py`, the single source of truth for the manifest→language rule table, over the unit's `tree_file`, and takes its scope patterns for that language: {unitsFile} holds each unit's `language`, `language_detection` and `scope`.

It passes no workspace signal: a workspace root's language would answer for every unit of the workspace (a TypeScript package in a Cargo workspace would read as `rust`). The unit's folder is the tree's root for the helper, so the unit's own manifest decides, and a manifest in its docs, examples, tests or tools folder never does while another one exists. When a unit's `language_detection.detected_languages` has more than one entry, its `language` is the helper's first guess: choose the language the unit documents from its own manifest (the unit's `manifest`), or, without one, `.source_language` (the language most of its files are written in), write it in the unit's judgment as `"language"`, run §3's call again, and name the choice and the other languages in §6. When `language_detection.confidence` is low (the extension-frequency fallback fired: no manifest matched), surface it in §6 so the user can override the guess.

A unit's `scope` `include` and `exclude` are its brief `scope.include` and `scope.exclude` for its language (a language outside the helper's choices passes `unknown`), rooted at the unit's folder, since the list's paths are under the scan root as a brief's are under its project path.

### 5. Defer What the Goal Leaves Out

Interactive runs only, and only when `intent_hint` is not empty: mark each qualifying unit the stated goal clearly leaves out `deferred` (its judgment's `status`), with one line on why at the end of its `rationale` (for example "deferred: payments, outside the stated goal (authentication)"), and run §3's call again. Step 4 maps only the units that are not deferred, and the deferred ones stay in the classification table, so nothing is dropped without notice. A unit you are unsure about stays in. A headless run defers nothing: there `intent_hint` only ranks the step 5 recommendations.

### 6. Present the Classifications and Confirm

Show the user the three tables §3's call printed last, then:

- **Mixed cases** (`stats.mixed`): for each qualifying unit with generated files, its name, `generated_ratio`, the flagged folders or headers and why it stays; and each boundary §2 Step B restored, with the files that restored it
- **Disqualified candidates**, with the table above
- **Already-skilled units** (from `existing_skills`), each with a recommendation to run update-skill if its source changed
- **Deferred units**, when §5 deferred any, with how to restore them
- **Notes:** structure patterns observed, and ambiguous boundaries that need the user's call

Then display:

"Add, remove, reclassify or restore any unit? Tell me, or **Select:** [C] Continue to Export Mapping and Integration Detection | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: go to §7
- IF X: HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `identify-units:6`): "Cancelled at unit identification."
- IF Any other: adjust the judgments in `{run_dir}/unit-judgments.json` as directed (restoring a deferred unit sets its status back to new or briefed) and run §3's call again, which prints the tables anew. A unit this adds or restores from the Disqualification table takes its language and scope patterns by §4, its demo and registry counts by Step E and its name by Step C's call run again with its entry added to the others (one added by path first joins the end of its project path's Step A list, and that call runs again), and a unit given another language takes its scope patterns again for that language. Show what changed, then [Redisplay Menu Options](#6-present-the-classifications-and-confirm)

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: accept every classification and continue with [C], and record that decision the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "identify-units.classifications", "default_action": "C", "taken_action": "C", "reason": "headless: auto-accept unit classifications", "evidence": {"qualifying": <the qualifying unit count>, "dropped": <the dropped boundary count>}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost.

### 7. Append to Report and Continue

Replace the placeholder `[Appended by identify-units]` in {outputFile} (or, when continue.md sent back a report without {unitsFile}, what its Identified Units section holds) with:
- The three tables §3's call printed last, as printed: the classification table (deferred units included), the language results with each unit's `tree_file` and scope patterns (`include` and `exclude`), and the Disqualification table
- Mixed cases and restored boundaries, with their evidence
- Already-skilled units list
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'identify-units' to existing array]
lastStep: 'identify-units'
```

Then load, read the entire file, then execute {nextStepFile}.

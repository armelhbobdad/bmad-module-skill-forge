---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
scanRootFile: 'references/scan-root.md'
disqualifyCandidatesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-disqualify-candidates.py'
  - '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
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

**A scan root that is gone.** A session that resumed this report runs in a new run folder, and the folder of the session that made a copy may be gone. When a recorded scan root no longer exists, make it again by {scanRootFile} into this run's `{run_dir}/source-{i}` and update `scan_roots` in {outputFile}'s frontmatter. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `identify-units:1`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

Load {heuristicsFile} for classification rules.

### 2. Apply Detection Heuristics

**Resolve `{disqualifyCandidatesHelper}`** from `{disqualifyCandidatesProbeOrder}` and **`{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `identify-units:2`): "`{the missing script}` is missing. Re-install SKF."

For each detected boundary from the scan, apply the classification rules from {heuristicsFile} (loaded in §1):

**Step A: Run the disqualification helper (script).** In one call per project path it lists each boundary's files itself, applies the deterministic subset of the rules from {heuristicsFile} (file count, LoC, generated files) and looks up the signal files and the boundary's own manifest. Its output is evidence that Step B judges, not a verdict.

Run it once per project path, the `{i}`-th entry of `project_paths[]`, over the boundaries found under it, with `{scan_root}` that path's scan root (never `{project-root}`, the forge workspace) and one entry per boundary, its path relative to the scan root (`.` for a boundary at the root), with forward slashes:

```bash
uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root "{scan_root}" --tree-dir "{run_dir}/unit-trees/{i}" <<'SKF_BOUNDARIES'
[{"name": "<boundary folder name>", "path": "<boundary path>"}, ...]
SKF_BOUNDARIES
```

1. The script lists every boundary's files (what git lists under its path, so ignored build output and installed dependencies stay out), writes each list to the run folder and emits one record per boundary:
   ```json
   {
     "kept":    [{"name": "...", "path": "...", "files_count": N, "loc_total": L, "non_source_count": K,
                  "generated_files": [{"path": "...", "reason": "generated-code|auto-generated-tag", "match": "..."}],
                  "generated_ratio": R, "passes_with_generated": true,
                  "manifest": {"path": "...", "ecosystem": "npm", "name": "@acme/auth", "private": false},
                  "signals": {...}, "tree_file": "..."}, ...],
     "dropped": [{"name": "...", "reason": "<too-few-files|too-low-loc|generated-code|auto-generated-tag>", "context": {...}, ...}, ...],
     "stats":   {"kept": N, "dropped": N, "mixed": N, "by_reason": {"<reason>": N, ...}}
   }
   ```
   A `dropped[]` record carries every `kept[]` field plus `reason` and `context`. Read `files_count` and `loc_total` (the boundary's own source files, counted as {heuristicsFile}'s Disqualification Rules say), `generated_files` and `generated_ratio` (the files Step B weighs), `passes_with_generated` (whether the size rules pass with those files counted too), `manifest` (the boundary's own manifest, null without one), `signals` (Step D) and `tree_file` (the boundary's file list, which §4 hands to the language helper).
2. A boundary path that is no folder under the scan root makes the script exit 1 and name it on stderr: correct that entry and run the call again.
3. **Stash the results** in workflow state, each record with its project path: `kept[]` is the candidate pool for the classification that follows, and `dropped[]` drives the Disqualification table.

**Step B: Judge what the script cannot.**

- **Mixed cases** (`stats.mixed` counts them): a kept boundary whose `generated_files` is not empty. Read the flagged paths and their `match`. Build output or a vendored copy beside the unit's own code leaves the unit standing, and its counts already leave those files out. Drop a mixed boundary only when its own code is no more than glue around the generated files, with reason `generated-code` and one line on why.
- **A drop the flagged files caused:** a boundary dropped as `generated-code`, `auto-generated-tag`, `too-few-files` or `too-low-loc` whose `generated_files` you judge to be its own code (a source folder named `build/` or `dist/`, a header its own tooling writes into code it maintains) goes back into `kept[]` when its `passes_with_generated` is true, with those files named in the notes. When it is false, the boundary stays dropped: even with those files it is too small.
- **LLM-judged disqualifications** (not in the script; apply on top of `kept[]`), removing a boundary that fails one from the working `kept` set and appending it to `dropped[]` with the reason:
  - **Pure configuration**: only config files (e.g., `.json`/`.yaml`) with no executable logic
  - **Test-only**: test utilities with no production code

Show every drop and every restore in §6 with its reason and evidence (the record's `context`, `generated_ratio` and first `generated_files` path), so the user can override it; a headless run keeps the judgment made here.

**Step C: Name each unit (script), then check it is not already skilled.** The helper that names every brief names the units too, so a unit's name here is the name its brief gets.

1. Name every unit in one call, by {heuristicsFile}'s Unit Names, one entry per kept boundary straight from its record: `target` is its `path` (its project path itself for a boundary at the root), and `manifest_name` and `private` are its `manifest.name` and `manifest.private` (null when `manifest` is null):
   ```bash
   uv run {skillInventoryHelper} derive-name --from - <<'SKF_UNIT_NAMES'
   [{"target": "<boundary path>", "manifest_name": <manifest.name>, "private": <manifest.private>}, ...]
   SKF_UNIT_NAMES
   ```
   Each `names[].name` is that unit's name from here on. Boundaries whose names would clash are already told apart by their parent folders (`clash` keeps the name they shared); give the entries `unnamed` and `duplicates` list a name of your own, from their folder.
2. **Already skilled:** a unit whose name is in `existing_skills` (a compiled skill) fails the last LLM-judged rule: remove it from the working `kept` set and append it to `dropped[]` with reason `already-skilled` (recommend `update-skill` instead). A unit whose name is in `existing_briefs` only has a brief from an earlier analysis: it stays a candidate with status `briefed` and its brief's path, and generate-briefs rewrites that brief only if the unit is confirmed.

**Step D: Tally detection signals** per the Detection Signals tables in {heuristicsFile}: cite the file each record's `signals` entry names (and `large_directory`), and judge the signals the helper does not report, as that file says.

**Step E: Classify boundary type** per its Boundary Classification section, and **assign the scope type** from that same section for the boundary's type. This pass classifies each boundary on its own: composite merges are proposed in map-and-detect, once the import graph exists.

### 3. Build Unit Classification Table

For each candidate that passes disqualification:

| # | Unit Name | Project Path | Path | Boundary Type | Scope Type | Files | Own Manifest | Signals | Confidence | Status |
|---|-----------|--------------|------|---------------|------------|-------|--------------|---------|------------|--------|
| 1 | {name} | {its project path} | {path} | {type} | {scope} | {files_count} | {manifest path, name and ecosystem, or --} | {signal count: strong/moderate/weak} | {high/medium/low} | {new/briefed/deferred} |

For disqualified candidates, note reason and evidence:

**Disqualified:**
| Path | Reason | Evidence |
|------|--------|----------|
| {path} | {disqualification reason} | {the record's `context`, or `generated_ratio` and the first `generated_files` path} |

### 4. Detect Primary Language Per Unit

For each qualifying unit, detect the primary language deterministically via the shared helper, the single source of truth for the manifest→language rule table.

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins. If neither exists, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `identify-units:4`): "`skf-detect-language.py` is missing. Re-install SKF."

For each unit, hand the helper the file list §2 wrote for it, its record's `tree_file`:

```bash
uv run {detectLanguageHelper} --tree-file "{the unit's tree_file}"
```

Pass no `--workspace-signal` here: a workspace root's language would answer for every unit of the workspace (a TypeScript package in a Cargo workspace would read as `rust`). The unit's folder is the tree's root for the helper, so the unit's own manifest decides, and a manifest in its docs, examples, tests or tools folder never does while another one exists. Read `.language` and `.confidence` for the unit. When `detected_languages` has more than one entry, `.language` is the helper's first guess: choose the language the unit documents from its own manifest (the record's `manifest`), or, without one, `.source_language` (the language most of its files are written in), and name the choice and the other languages in §6. When confidence is low (the extension-frequency fallback fired: no manifest matched), surface it in §6 so the user can override the guess.

### 5. Defer What the Goal Leaves Out

Interactive runs only, and only when `intent_hint` is not empty: mark each qualifying unit the stated goal clearly leaves out `deferred` in the Status column, with one line on why (for example "deferred: payments, outside the stated goal (authentication)"). Step 4 maps only the units that are not deferred, and the deferred ones stay in the classification table, so nothing is dropped without notice. A unit you are unsure about stays in. A headless run defers nothing: there `intent_hint` only ranks the step 5 recommendations.

### 6. Present the Classifications and Confirm

Show the user the classification table, then:

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
- IF Any other: adjust the classifications as directed (restoring a deferred unit sets its status back to new or briefed), show what changed, then [Redisplay Menu Options](#6-present-the-classifications-and-confirm)

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: accept every classification and continue with [C], and record that decision the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "identify-units.classifications", "default_action": "C", "taken_action": "C", "reason": "headless: auto-accept unit classifications", "evidence": {"qualifying": <the qualifying unit count>, "dropped": <the dropped boundary count>}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost.

### 7. Append to Report and Continue

Replace the placeholder `[Appended by identify-units]` in {outputFile} with:
- Classification table (qualifying units, under their §2 Step C names, with their project paths, file counts, own manifests and statuses, deferred units included)
- Mixed cases and restored boundaries, with their evidence
- Disqualification table
- Already-skilled units list
- Language detection results, and each unit's `tree_file`
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'identify-units' to existing array]
lastStep: 'identify-units'
```

Then load, read the entire file, then execute {nextStepFile}.

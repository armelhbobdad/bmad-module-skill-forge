---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: '{unitDetectionHeuristicsPath}'
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

To classify each detected boundary from the project scan into discrete skillable units by applying detection heuristics, assigning boundary types and scope types, and filtering out disqualified candidates.

## Rules

- Focus only on unit classification — do not map exports or integration points yet
- Do not generate skill-brief.yaml in this step
- Every classification must cite the detection signals that justify it

## MANDATORY SEQUENCE

### 1. Load Context

Read {outputFile} to obtain:
- Project Scan results (detected boundaries, manifests, entry points)
- `forge_tier` from frontmatter
- `existing_skills` from frontmatter

Load {heuristicsFile} for classification rules.

### 2. Apply Detection Heuristics

**Resolve `{disqualifyCandidatesHelper}`** from `{disqualifyCandidatesProbeOrder}` and **`{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT with exit code 3 (`resolution-failure`) and the error envelope on stderr (shape in `references/headless-contract.md`).

For each detected boundary from the scan, apply the classification rules from {heuristicsFile} (loaded in §1):

**Step A: Run the disqualification helper (script).** In one call it applies the deterministic subset of the rules from {heuristicsFile} (file count, LoC, generated files) and looks up the signal files and the boundary's own manifest: work with one right answer per file list. Its output is evidence that Step B judges, not a verdict.

1. **Build the boundaries JSON** from the detected boundaries (one entry per candidate boundary). Use forward-slash paths throughout. Shape:
   ```json
   [
     {"name": "<unit-name>",
      "path": "<rel-from-analyzed-source-root (project_paths[0])>",
      "files": ["<rel-from-analyzed-source-root>", ...]},
     ...
   ]
   ```
2. **Invoke the script** via stdin:
   ```bash
   uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root {project_paths[0]}
   ```
   piping the boundaries JSON on stdin. `--source-root` is the analyzed-source root (`project_paths[0]`), the directory the boundaries/manifest scan ran against, not `{project-root}` (the forge workspace), which differs whenever the analyzed target lives outside the forge workspace. The script emits one record per boundary:
   ```json
   {
     "kept":    [{"name": "...", "path": "...", "files_count": N, "loc_total": L, "non_source_count": K,
                  "generated_files": [{"path": "...", "reason": "generated-code|auto-generated-tag", "match": "..."}],
                  "generated_ratio": R, "passes_with_generated": true,
                  "manifest": {"path": "...", "ecosystem": "npm", "name": "@acme/auth", "private": false},
                  "signals": {...}}, ...],
     "dropped": [{"name": "...", "reason": "<too-few-files|too-low-loc|generated-code|auto-generated-tag>", "context": {...}, ...}, ...],
     "stats":   {"kept": N, "dropped": N, "mixed": N, "by_reason": {"<reason>": N, ...}}
   }
   ```
   A `dropped[]` record carries every `kept[]` field plus `reason` and `context`. Read `files_count` and `loc_total` (the boundary's own source files, counted as {heuristicsFile}'s Disqualification Rules say), `generated_files` and `generated_ratio` (the files Step B weighs), `passes_with_generated` (whether the size rules pass with those files counted too), `manifest` (the boundary's own manifest, null without one) and `signals` (Step D).
3. **Parse the JSON result** and stash `kept[]` and `dropped[]` in workflow state for §3 (classification table) and §5 (recommendation summary). The `kept` set is the candidate pool for the classification that follows; the `dropped` set drives the Disqualification table.

**Step B: Judge what the script cannot.**

- **Mixed cases** (`stats.mixed` counts them): a kept boundary whose `generated_files` is not empty. Read the flagged paths and their `match`. Build output or a vendored copy beside the unit's own code leaves the unit standing, and its counts already leave those files out. Drop a mixed boundary only when its own code is no more than glue around the generated files, with reason `generated-code` and one line on why.
- **A drop the flagged files caused:** a boundary dropped as `generated-code`, `auto-generated-tag`, `too-few-files` or `too-low-loc` whose `generated_files` you judge to be its own code (a source folder named `build/` or `dist/`, a header its own tooling writes into code it maintains) goes back into `kept[]` when its `passes_with_generated` is true, with those files named in the notes. When it is false, the boundary stays dropped: even with those files it is too small.
- **LLM-judged disqualifications** (not in the script; apply on top of `kept[]`), removing a boundary that fails one from the working `kept` set and appending it to `dropped[]` with the reason:
  - **Pure configuration**: only config files (e.g., `.json`/`.yaml`) with no executable logic
  - **Test-only**: test utilities with no production code

Show every drop and every restore in §5 with its reason and evidence (the record's `context`, `generated_ratio` and first `generated_files` path), so the user can override it; a headless run keeps the judgment made here.

**Step C: Name each unit (script), then check it is not already skilled.** The helper that names every brief names the units too, so a unit's name here is the name its brief gets.

1. Name every unit in one call, by {heuristicsFile}'s Unit Names, one entry per kept boundary straight from its record: `target` is its `path` (`{project_paths[0]}` for a boundary at the root), and `manifest_name` and `private` are its `manifest.name` and `manifest.private` (null when `manifest` is null):
   ```bash
   uv run {skillInventoryHelper} derive-name --from - <<'SKF_UNIT_NAMES'
   [{"target": "<boundary path>", "manifest_name": <manifest.name>, "private": <manifest.private>}, ...]
   SKF_UNIT_NAMES
   ```
   Each `names[].name` is that unit's name from here on. Boundaries whose names would clash are already told apart by their parent folders (`clash` keeps the name they shared); give the entries `unnamed` and `duplicates` list a name of your own, from their folder.
2. **Already skilled:** a unit whose name is in `existing_skills` fails the last LLM-judged rule: remove it from the working `kept` set and append it to `dropped[]` with reason `already-skilled` (recommend `update-skill` instead).

**Step D: Tally detection signals** per the Detection Signals tables in {heuristicsFile}: cite the file each record's `signals` entry names (and `large_directory`), and judge the signals the helper does not report, as that file says.

**Step E: Classify boundary type** per its Boundary Classification section, and **assign the scope type** from that same section for the boundary's type. This pass classifies each boundary on its own: composite merges are proposed in map-and-detect, once the import graph exists.

### 3. Build Unit Classification Table

For each candidate that passes disqualification:

| # | Unit Name | Path | Boundary Type | Scope Type | Files | Own Manifest | Signals | Confidence | Status |
|---|-----------|------|---------------|------------|-------|--------------|---------|------------|--------|
| 1 | {name} | {path} | {type} | {scope} | {files_count} | {manifest path, name and ecosystem, or --} | {signal count: strong/moderate/weak} | {high/medium/low} | {new/already-skilled} |

For disqualified candidates, note reason and evidence:

**Disqualified:**
| Path | Reason | Evidence |
|------|--------|----------|
| {path} | {disqualification reason} | {the record's `context`, or `generated_ratio` and the first `generated_files` path} |

### 4. Detect Primary Language Per Unit

For each qualifying unit, detect the primary language deterministically via the shared helper, the single source of truth for the manifest→language rule table.

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins.

For each unit, pipe its file list — the `files` array built for that boundary in the §2 boundaries JSON — as the tree:

```bash
echo '{"tree": [<unit files — forward-slash, repo-relative>]}' | uv run {detectLanguageHelper}
```

Read `.language` and `.confidence` for the unit. When confidence is low (the extension-frequency fallback fired — no manifest matched), surface it in §5 so the user can override the guess.

### 5. Present Classifications

"**Unit Identification Complete**

**Qualifying Units:** {count}

{Classification table}

**Mixed Cases:** {count}
{For each qualifying unit with generated files: its name, `generated_ratio`, the flagged folders or headers, and why it stays; and each boundary §2 Step B restored, with the files that restored it}

**Disqualified Candidates:** {count}
{Disqualification table}

**Already-Skilled Units:** {count from existing_skills match}
{List with recommendation to run update-skill if source has changed}

**Notes:**
- {Any observations about project structure patterns}
- {Any ambiguous boundaries that need user clarification}

Do these classifications look correct? Should any units be added, removed, or reclassified?"

Wait for user feedback. Adjust classifications based on user input.

### 6. Append to Report

Append the complete "## Identified Units" section to {outputFile}:

Replace the placeholder `[Appended by identify-units]` with:
- Classification table (qualifying units, under their §2 Step C names, with their file counts and own manifests)
- Mixed cases and restored boundaries, with their evidence
- Disqualification table
- Already-skilled units list
- Language detection results
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'identify-units' to existing array]
lastStep: 'identify-units'
```

### 7. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Export Mapping and Integration Detection | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Save classifications to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF X: HARD HALT with exit code 6 (`user-cancelled`). Emit the error envelope on stderr with `halt_reason: "user-cancelled"` and counts/paths reflecting state at cancellation (shape in `references/headless-contract.md`)
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

**GATE [default: C]** — present the menu and wait for the user's choice. If `{headless_mode}`: accept all classifications and auto-proceed, log: "headless: auto-accept unit classifications".


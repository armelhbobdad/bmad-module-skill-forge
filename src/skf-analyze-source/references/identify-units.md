---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
disqualifyCandidatesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-disqualify-candidates.py'
  - '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
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

**Resolve `{disqualifyCandidatesHelper}`** from `{disqualifyCandidatesProbeOrder}`; first existing path wins. HALT if no candidate exists.

For EACH detected boundary from the scan:

**Step A — Count detection signals:**
- Check strong signals (independent manifest, separate entry point, Docker config, distinct export surface, workspace member)
- Check moderate signals (directory depth, naming convention, separate tests, README, CI/CD reference)
- Check weak signals (large directory, comment boundaries, import clustering)

**Step B — Classify boundary type:**
- Service Boundary — independent deployable unit
- Package Boundary — workspace member or independently versioned
- Module Boundary — logical grouping within a package
- Library Boundary — third-party with significant project-specific usage
- Composite Boundary — ≥2 boundaries that only deliver value together (detected in §3b below; not assigned during initial per-boundary classification)

**Step C — Assign scope type:**
- `full-library` — entire codebase of the unit
- `specific-modules` — selected components or packages
- `public-api` — only exported interfaces

**Step D — Run deterministic disqualification filter (script):**

Run the shared disqualification helper to apply the deterministic subset of the rules from {heuristicsFile} (file-count, LoC, generated-code paths, auto-generated header sentinels). The script collapses what was prose-orchestrated counting + path-substring + header scanning into one deterministic call.

1. **Build the boundaries JSON** from the detected boundaries (one entry per candidate boundary). Use forward-slash paths throughout. Shape:
   ```json
   [
     {"name": "<unit-name>",
      "path": "<rel-from-analyzed-source-root (project_paths[0])>",
      "files": ["<rel-path>", ...]},
     ...
   ]
   ```
2. **Invoke the script** via stdin:
   ```bash
   uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root {project_paths[0]}
   ```
   piping the boundaries JSON on stdin. `--source-root` is the analyzed-source root (`project_paths[0]`) — the directory the boundaries/manifest scan ran against — not `{project-root}` (the forge workspace), which differs whenever the analyzed target lives outside the forge workspace. The script emits:
   ```json
   {
     "kept":    [{"name": "...", "path": "...", "files_count": N, "loc_total": L}, ...],
     "dropped": [{"name": "...", "reason": "<too-few-files|too-low-loc|generated-code|auto-generated-tag>", "context": {...}}, ...],
     "stats":   {"kept": N, "dropped": N, "by_reason": {"<reason>": N, ...}}
   }
   ```
3. **Parse the JSON result** and stash `kept[]` and `dropped[]` in workflow state for §3 (classification table) and §5 (recommendation summary). The `kept` set is the candidate pool for the boundary-type + scope-type classification that follows; the `dropped` set drives the Disqualification table.

**LLM-judged disqualifications (not in script — apply on top of `kept[]`):**
- **Pure configuration** — only config files (e.g., `.json`/`.yaml`) with no executable logic
- **Test-only** — test utilities with no production code
- **Already skilled** — exists in `existing_skills` list (recommend `update-skill` instead)

Remove any boundary that fails one of these LLM-judged rules from the working `kept` set and append it to `dropped[]` with the appropriate reason. Reasons recorded by the script (`too-few-files`, `too-low-loc`, `generated-code`, `auto-generated-tag`) are authoritative; do NOT re-evaluate those rules manually.

**Qualification CONFIRMATION:** Visually skim the script's `kept`/`dropped` decisions for sanity (e.g., a boundary you expected to qualify that landed in `dropped` — surface the script's `reason` and `context.first_match` to the user in §5 so they can override if the heuristic was wrong for this project).

### 3. Build Unit Classification Table

For each candidate that passes disqualification:

| # | Unit Name | Path | Boundary Type | Scope Type | Signals | Confidence | Status |
|---|-----------|------|---------------|------------|---------|------------|--------|
| 1 | {name} | {path} | {type} | {scope} | {signal count: strong/moderate/weak} | {high/medium/low} | {new/already-skilled} |

For disqualified candidates, note reason:

**Disqualified:**
| Path | Reason |
|------|--------|
| {path} | {disqualification reason} |

### 3b. Detect Composite Unit Merges

After building the classification table, apply the Composite Boundary detection heuristic from {heuristicsFile} against the qualifying units:

1. **Scan for merge candidates:** Among the qualifying units (from `kept[]`), find groups of ≥2 Package or Module boundaries that meet EITHER trigger:
   - **Mutual hard dependency:** Every constituent imports from at least one other constituent in the group, AND no constituent's public API is self-contained
   - **Shared integration surface:** Constituents share types/traits defined in one constituent but consumed by all others, AND the consuming constituents have no independent barrel

2. **If candidate groups are found**, propose each merge:
   - Derive a composite name from the common namespace prefix or repo name
   - List the constituents (boundary names and paths being merged)
   - State the triggering heuristic and evidence

3. **If no candidate groups are found**, skip to §4.

**Merge does NOT fire for:** Units already flagged as Stack Skill Candidates in step 4 (map-and-detect §5) — those are multi-unit groupings that deliver value *separately* but are *also* useful together. Composite merges are for units that are *only* useful together (the key distinction). If a group of units is independently useful but commonly combined, it remains as separate units and is flagged as a stack skill candidate later.

**This step is a recommendation — not automatic.** Merges are presented to the user in §5 for confirmation (see "Composite Merge Proposals" below). If the user rejects a merge, the constituents remain as separate units in the classification table.

### 4. Detect Primary Language Per Unit

For each qualifying unit (including any approved composites from §3b), determine the primary programming language based on:
- File extensions in the unit directory
- Manifest file type (package.json → JS/TS, Cargo.toml → Rust, go.mod → Go, etc.)
- Entry point file extension

### 5. Present Classifications

"**Unit Identification Complete**

**Qualifying Units:** {count}

{Classification table}

**Disqualified Candidates:** {count}
{Disqualification table}

**Already-Skilled Units:** {count from existing_skills match}
{List with recommendation to run update-skill if source has changed}

{IF composite merge proposals exist from §3b:}

**Composite Merge Proposals:** {count}

| # | Composite Name | Constituents | Heuristic | Evidence |
|---|----------------|--------------|-----------|----------|
| 1 | {name} | {list of constituent unit names} | {mutual hard dependency / shared integration surface} | {brief evidence} |

If approved, each composite replaces its constituents in the classification table as a single Composite Boundary unit. The constituents are recorded in the composite's metadata for downstream workflows (create-skill reads constituents to scope extraction across all member paths).

{END IF}

**Notes:**
- {Any observations about project structure patterns}
- {Any ambiguous boundaries that need user clarification}

Do these classifications look correct? Should any units be added, removed, or reclassified?
{IF composites proposed:} Are the composite merge proposals correct? (Accept/reject each individually.)"

Wait for user feedback. Adjust classifications based on user input. For approved composites: remove the constituent rows from the qualifying units table and add a single composite row with `Boundary Type: Composite`, scope type inherited from the dominant constituent, and confidence reflecting the merge heuristic strength.

### 6. Append to Report

Append the complete "## Identified Units" section to {outputFile}:

Replace the placeholder `[Appended by identify-units]` with:
- Classification table (qualifying units, including approved composites)
- Composite merge details (if any): composite name, constituents list, heuristic, evidence
- Disqualification table
- Already-skilled units list
- Language detection results
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'identify-units' to existing array]
lastStep: 'identify-units'
confirmed_composites: [{list of approved composite merge objects: {name, constituents[], heuristic}}]
```

(`confirmed_composites` is an empty array when no composites were proposed or all were rejected.)

### 7. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Export Mapping and Integration Detection | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Save classifications to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF X: HARD HALT with exit code 6 (`user-cancelled`). Emit the `SKF_ANALYZE_RESULT_JSON` envelope on stderr with `status: "error"`, `halt_reason: "user-cancelled"`, and counts/paths reflecting state at cancellation
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: accept all classifications and auto-proceed, log: "headless: auto-accept unit classifications"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the Identified Units section has been appended to {outputFile} with complete classification tables, disqualification records, and language detection results, and frontmatter stepsCompleted has been updated, will you load and read fully {nextStepFile} to begin export mapping and integration detection.


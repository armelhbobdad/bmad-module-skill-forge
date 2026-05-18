---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
disqualifyCandidatesScript: '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
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
      "path": "<rel-from-project-root>",
      "files": ["<rel-path>", ...]},
     ...
   ]
   ```
2. **Invoke the script** via stdin:
   ```bash
   uv run {disqualifyCandidatesScript} filter --boundaries - --source-root {project-root}
   ```
   piping the boundaries JSON on stdin. The script emits:
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

### 4. Detect Primary Language Per Unit

For each qualifying unit, determine the primary programming language based on:
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

**Notes:**
- {Any observations about project structure patterns}
- {Any ambiguous boundaries that need user clarification}

Do these classifications look correct? Should any units be added, removed, or reclassified?"

Wait for user feedback. Adjust classifications based on user input.

### 6. Append to Report

Append the complete "## Identified Units" section to {outputFile}:

Replace the placeholder `[Appended by identify-units]` with:
- Classification table (qualifying units)
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
- IF X: HARD HALT with exit code 6 (`user-cancelled`). Emit the `SKF_ANALYZE_RESULT_JSON` envelope on stderr with `status: "error"`, `halt_reason: "user-cancelled"`, and counts/paths reflecting state at cancellation
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: accept all classifications and auto-proceed, log: "headless: auto-accept unit classifications"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the Identified Units section has been appended to {outputFile} with complete classification tables, disqualification records, and language detection results, and frontmatter stepsCompleted has been updated, will you load and read fully {nextStepFile} to begin export mapping and integration detection.


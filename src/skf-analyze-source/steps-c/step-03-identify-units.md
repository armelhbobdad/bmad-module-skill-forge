---
nextStepFile: './step-04-map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
---

# Step 3: Identify Units

## STEP GOAL:

To classify each detected boundary from the project scan into discrete skillable units by applying detection heuristics, assigning boundary types and scope types, and filtering out disqualified candidates.

## Rules

- Focus only on unit classification — do not map exports or integration points yet
- Do not generate skill-brief.yaml in this step
- Every classification must cite the detection signals that justify it

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

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

**Step D — Check disqualification rules:**
- Too small (fewer than 3 source files or 100 lines)
- Generated code
- Pure configuration
- Test-only
- Vendor/dependency copy
- Already skilled (exists in existing_skills list)

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

Replace the placeholder `[Appended by step-03-identify-units]` with:
- Classification table (qualifying units)
- Disqualification table
- Already-skilled units list
- Language detection results
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'step-03-identify-units' to existing array]
lastStep: 'step-03-identify-units'
```

### 7. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Export Mapping and Integration Detection"

#### Menu Handling Logic:

- IF C: Save classifications to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: accept all classifications and auto-proceed, log: "headless: auto-accept unit classifications"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the Identified Units section has been appended to {outputFile} with complete classification tables, disqualification records, and language detection results, and frontmatter stepsCompleted has been updated, will you load and read fully {nextStepFile} to begin export mapping and integration detection.


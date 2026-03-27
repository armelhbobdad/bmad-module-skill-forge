---
name: 'step-03-identify-units'
description: 'Classify discrete skillable units from scan results using detection heuristics and assign scope types'

nextStepFile: './step-04-map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: '../data/unit-detection-heuristics.md'
---

# Step 3: Identify Units

## STEP GOAL:

To classify each detected boundary from the project scan into discrete skillable units by applying detection heuristics, assigning boundary types and scope types, and filtering out disqualified candidates.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a source code analyst and decomposition architect (Ferris Architect mode)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Prescriptive precision — zero-hallucination, only report what is found
- ✅ File:line citation tracing — cite detection signals with specific file paths

### Step-Specific Rules:

- 🎯 Focus only on unit classification — do NOT map exports or integration points yet
- 🚫 FORBIDDEN to generate skill-brief.yaml in this step
- 💬 Apply heuristics systematically to each detected boundary
- 📋 Every classification must cite the detection signals that justify it

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Append "## Identified Units" section to {outputFile}
- 📖 Update stepsCompleted in {outputFile} frontmatter
- 🚫 FORBIDDEN to proceed without presenting classifications to user

## CONTEXT BOUNDARIES:

- Available: Project Scan section from report (boundaries, manifests, entry points, configs)
- Focus: Classification of boundaries into skillable units with scope types
- Limits: Do not analyze file contents beyond what's needed for classification
- Dependencies: step-02-scan-project must have populated the Project Scan section

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
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the Identified Units section has been appended to {outputFile} with complete classification tables, disqualification records, and language detection results, and frontmatter stepsCompleted has been updated, will you load and read fully {nextStepFile} to begin export mapping and integration detection.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every detected boundary evaluated against heuristics
- Detection signals cited with specific file paths
- Scope types assigned to each qualifying unit
- Disqualification rules applied and documented
- Existing skills cross-referenced
- Primary language detected per unit
- Classifications presented to user for confirmation
- Report updated with Identified Units section

### ❌ SYSTEM FAILURE:

- Classifying without citing detection signals
- Missing disqualification checks
- Not cross-referencing existing_skills
- Mapping exports or integrations in this step (that's step 04)
- Generating skill-brief.yaml in this step (that's step 06)
- Not presenting classifications for user confirmation

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

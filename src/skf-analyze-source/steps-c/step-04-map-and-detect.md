---
nextStepFile: './step-05-recommend.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
---

# Step 4: Map Exports and Detect Integrations

## STEP GOAL:

To analyze each qualifying unit's export surface and import graph, detect cross-unit integration points, and flag potential stack skill candidates — completing the analysis foundation needed for recommendations.

## Rules

- Use subprocess Pattern 2 (per-unit deep analysis) when available
- For each qualifying unit, perform thorough export surface analysis — do not shortcut
- Do not make recommendations (Step 05)
- Tier-aware depth: Quick (file-level), Forge (AST), Deep (AST + semantic)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Context

Read {outputFile} to obtain:
- Qualifying units from Identified Units section (names, paths, scope types, languages)
- `forge_tier` from frontmatter

Load {heuristicsFile} for stack skill candidate detection rules.

### 2. Map Export Surfaces Per Unit

DO NOT BE LAZY — For EACH qualifying unit, launch a subprocess (or analyze in main thread) that:

**Size-aware strategy selection:**
- **< 50 files:** Full export scan — analyze every file for exports
- **50-200 files:** Targeted scan — entry points (`__init__.py`, `index.ts`, `lib.rs`) + public modules + barrel exports only
- **200+ files:** Entry-point strategy — analyze top-level entry point for public API surface, list submodule entry points, analyze each submodule entry point only. Report coverage confidence based on percentage of files analyzed.

**Per-unit analysis (scaled by strategy above):**

1. Scans the unit's directory for export/public interface files
2. Counts and categorizes exports based on forge tier:
   - **Quick tier:** Count files by type, identify index/barrel files, list directory structure
   - **Forge tier:** Parse export statements, identify public API surface, count exported functions/classes/types
   - **Forge+ tier:** All Forge analysis plus:
     - If `tools.ccc` is true: run `ccc_bridge.search("{unit_name} exports public API", top_k=15)` — **Tool resolution:** `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search` CLI; see `knowledge/tool-resolution.md` — to discover semantically relevant files beyond directory scan
     - Merge CCC-discovered files with scoped file list — files from CCC that are within the unit's directory are added to the analysis queue
     - Record CCC signals in per-unit findings: top 3 CCC-ranked file names (or "—" if no ccc results)
   - **Deep tier:** All Forge analysis plus:
     - ast-grep structural export extraction: `ast-grep -p 'export $$$' --lang typescript` or equivalent per language to build a verified export inventory
     - ast-grep type/interface mapping: `ast-grep -p 'interface $NAME' --lang typescript` or `ast-grep -p 'class $NAME($$$)' --lang python`
     - If QMD available: query for temporal evolution of identified exports (deprecation signals, recent additions, refactoring patterns)
     - Record semantic relationships between exports (which exports reference/depend on each other)
3. Returns structured findings to parent:
   - Export count (files, functions, types, classes)
   - Primary export patterns (barrel exports, direct exports, re-exports)
   - Public API surface size estimate
   - Key entry points
   - Script/asset presence: check for `scripts/`, `bin/`, `assets/`, `templates/` directories and files matching detection signals in `{heuristicsFile}`. Record counts in per-unit findings.
   - Analysis strategy used and coverage confidence

**Per-unit export summary:**

| Unit | Files | Exports | Export Pattern | API Surface | Scripts/Assets | CCC Signals |
|------|-------|---------|----------------|-------------|----------------|-------------|
| {name} | {count} | {count} | {pattern} | {small/medium/large} | {N scripts, M assets or --} | {CCC signals or --} |

### 3. Map Import Graph

For each qualifying unit, analyze inbound and outbound imports:

**Outbound imports (this unit imports from):**
- Which other qualifying units does it depend on?
- Which external dependencies does it use?

**Inbound imports (other units import from this):**
- Which other qualifying units consume this unit's exports?
- How many import sites exist?

**Build cross-reference matrix:**

| Unit | Imports From | Imported By | External Deps |
|------|-------------|-------------|---------------|
| {name} | {list units} | {list units} | {count} |

### 4. Detect Integration Points

Identify cross-unit integration patterns:

**Direct integrations:**
- Unit A imports from Unit B → document the interface boundary
- Shared type definitions across units
- Cross-unit function calls

**For each integration point document:**
- Source unit → Target unit
- Integration type (import, shared types, API call, message passing, shared state)
- Files involved (with paths)
- Coupling strength (tight / loose / indirect)

### 5. Flag Stack Skill Candidates

Using rules from {heuristicsFile}, check for stack skill indicators:

1. **Co-import frequency:** Two or more units imported together in 3+ files
2. **Integration adapter:** A unit exists primarily to bridge two other units
3. **Shared state:** Multiple units read/write to the same data store
4. **Orchestration layer:** A unit coordinates calls across multiple other units

**For each candidate, document:**
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

**Stack Skill Candidates:** {count}
{List each candidate with units involved and detection signal}

**Observations:**
- {Key architectural patterns observed}
- {Tightly coupled areas}
- {Loosely coupled areas ideal for independent skills}

Does this analysis look complete? Any integration patterns I should investigate further?"

Wait for user feedback. Adjust analysis based on user input.

### 7. Append to Report

Append the complete "## Export Map" section to {outputFile}:
Replace `[Appended by step-04-map-and-detect]` under Export Map with:
- Per-unit export summary table
- Export pattern analysis

Append the complete "## Integration Points" section to {outputFile}:
Replace `[Appended by step-04-map-and-detect]` under Integration Points with:
- Cross-reference matrix
- Integration point details
- Stack skill candidate flags

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'step-04-map-and-detect' to existing array]
lastStep: 'step-04-map-and-detect'
stack_skill_candidates: [{list flagged candidate groupings}]
```

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Recommendations | [D] Discover Additional Source"

#### Menu Handling Logic:

- IF C: Save findings to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF D: Accept a new repo path/URL from the user. Run a lightweight scan (directory structure + manifest detection from step 02) and classify (unit identification from step 03) for the new source only. Merge results into the existing report — append new units to the unit list, update `project_paths[]` in frontmatter. Then redisplay this step's export mapping for the new units before returning to the menu.
- IF Any other: help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN both the Export Map and Integration Points sections have been appended to {outputFile} with complete findings, and frontmatter stepsCompleted and stack_skill_candidates have been updated, will you load and read fully {nextStepFile} to begin recommendations.


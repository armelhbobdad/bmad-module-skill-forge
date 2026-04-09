---
nextStepFile: './step-03-identify-units.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
---

# Step 2: Scan Project

## STEP GOAL:

To map the complete project structure by scanning directory trees, detecting service boundaries, identifying package manifests, and cataloging entry points — building the foundation that subsequent steps use for unit identification.

## Rules

- Focus only on structural scanning — do not classify units or map exports yet
- Do not read source file contents beyond manifest files and entry points
- Use subprocess Pattern 1 for scanning across many files
- Tier-aware scanning depth: Quick (file structure), Forge (+ manifest parsing), Deep (+ config analysis)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Context

Read {outputFile} frontmatter to obtain:
- `project_paths[]` — the root(s) to scan (one or more paths/URLs)
- `forge_tier` — determines scanning depth
- Scope hints (if any were provided in step 01)

Load {heuristicsFile} for reference on detection signals.

### 2. Scan Directory Structure

**For each path in `project_paths[]`**, launch a subprocess that scans the project directory structure (aggregate results across all repos with clear repo-level grouping):

1. Map the top-level directory tree (2-3 levels deep)
2. Identify workspace configuration files (pnpm-workspace.yaml, lerna.json, Cargo.toml [workspace], go.work, etc.)
3. Find all package manifests (package.json, Cargo.toml, go.mod, requirements.txt, pyproject.toml, build.gradle, pom.xml)
4. Locate entry point files (index.ts, main.ts, app.ts, main.go, main.rs, __init__.py, etc.)
5. Detect service configuration (Dockerfile, docker-compose.yml, kubernetes manifests, serverless.yml)
6. Return structured findings — file paths and types only, not contents

**If subprocess unavailable:** Perform directory scanning in main thread using file I/O tools.

**Apply scope hints if provided:**
- If specific directories were given, scan only those
- If exclusion patterns were given, skip matching directories

**Deep tier additional scanning (IF Deep tier):**
- Use ast-grep to detect structural patterns across the codebase: `ast-grep -p 'class $NAME' --lang python` (or equivalent per language) to build a class/type inventory
- Use ast-grep to identify exported function patterns: `ast-grep -p 'def $FUNC($$$PARAMS)' --lang python` at entry points
- If QMD is available, query for temporal context on the project: recent changes, active development areas, refactoring patterns
- Record Deep-tier findings separately — they supplement (not replace) the Quick/Forge scan results

### 3. Detect Service Boundaries

Based on scan results, identify potential service boundaries:

**Strong boundary signals:**
- Independent package manifest (own package.json, Cargo.toml, etc.)
- Docker/container configuration
- Separate entry point file
- Workspace member listing

**Document each detected boundary with:**
- Path relative to project root
- Boundary type (service / package / module)
- Detection signals found (list specific files)
- Confidence level (strong / moderate / weak)

### 4. Catalog Manifests and Entry Points

Create a structured catalog:

**Manifests found:**
| Path | Type | Language Indicator |
|------|------|-------------------|
| {path} | {manifest_type} | {language} |

**Entry points found:**
| Path | Type |
|------|------|
| {path} | {entry_type} |

**Service configurations found:**
| Path | Type |
|------|------|
| {path} | {config_type} |

### 5. Present Scan Results

"**Project Scan Complete**

**Project:** {project_path}
**Forge Tier:** {forge_tier}

**Structure Overview:**
{top-level directory tree}

**Detected Boundaries:** {count}
{list each boundary with path, type, confidence}

**Manifests Found:** {count}
{summary table}

**Entry Points Found:** {count}
{summary table}

**Service Configurations:** {count}
{summary table}

**Scope Applied:** {hints or 'Full project scan'}

Does this scan look complete? Any directories I should investigate further or skip?"

Wait for user feedback. If user identifies gaps, rescan as directed.

### 6. Append to Report

Append the complete "## Project Scan" section to {outputFile}:

Replace the placeholder `[Appended by step-02-scan-project]` with the full scan results including:
- Structure overview
- Detected boundaries table
- Manifests catalog
- Entry points catalog
- Service configurations catalog
- Scope notes

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'step-02-scan-project' to existing array]
lastStep: 'step-02-scan-project'
```

### 7. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Unit Identification"

#### Menu Handling Logic:

- IF C: Save scan results to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past scan results"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the Project Scan section has been appended to {outputFile} with complete boundary, manifest, and entry point catalogs, and frontmatter stepsCompleted has been updated, will you load and read fully {nextStepFile} to begin unit identification.


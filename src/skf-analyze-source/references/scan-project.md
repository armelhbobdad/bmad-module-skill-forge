---
nextStepFile: 'identify-units.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
scanRootFile: 'references/scan-root.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Scan Project

## STEP GOAL:

To map the complete project structure by scanning directory trees, detecting service boundaries, identifying package manifests, and cataloging entry points — building the foundation that subsequent steps use for unit identification.

## Rules

- Focus only on structural scanning — do not classify units or map exports yet
- Do not read source file contents beyond manifest files and entry points
- Delegate per-file scanning to subagents in parallel when many files are involved (main-thread fallback is fine)
- Tier-aware scanning depth: Quick (file structure), Forge (+ manifest parsing), Deep (+ config analysis)

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Context

Read {outputFile} frontmatter to obtain:
- `project_paths[]`: the root(s) to scan (one or more paths/URLs)
- `refs`: each project path's ref (a path it leaves out has none)
- `forge_tier`: determines scanning depth
- `scope_hint`: the folders or packages to focus on or skip (may be empty)

Load {heuristicsFile} for reference on detection signals.

### 2. Scan Directory Structure

**Resolve `{scanManifestsHelper}`** from `{scanManifestsProbeOrder}`; first existing path wins. If no candidate exists, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `scan-project:2`): "`skf-scan-manifests.py` is missing. Re-install SKF."

**The scan root of each project path.** Every helper from here on reads a local folder, the path's **scan root**, which §6 records in `scan_roots` so the later steps read the same files. Load {scanRootFile} and make the scan root of each entry of `project_paths[]` as it says. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `scan-project:2`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

**For each path in `project_paths[]`**, scan its scan root (aggregate the results across all repos, grouped by project path):

1. Map the top-level directory tree (2-3 levels deep)
2. Identify workspace configuration files (pnpm-workspace.yaml, lerna.json, Cargo.toml [workspace], go.work, etc.)
3. Enumerate package manifests deterministically: invoke `uv run {scanManifestsHelper} scan "{scan_root}"` and parse the JSON envelope. The script returns `{manifests[], total_unique, monorepo, warnings?}` covering npm/python/rust/go/maven/gradle/ruby/composer/swift; record each `{path, ecosystem}` for the manifests catalog in §4 and capture `monorepo` for the boundary-signal pass in §3
4. Locate entry point files (index.ts, main.ts, app.ts, main.go, main.rs, __init__.py, etc.)
5. Detect service configuration (Dockerfile, docker-compose.yml, kubernetes manifests, serverless.yml): a file glob and a presence check, no parsing
6. Return structured findings (file paths and types only, not contents), one group per project path: `{path, ref, scan_root, manifests[], monorepo, warnings?}`

**If subprocess unavailable:** Perform directory scanning in main thread using file I/O tools.

**Apply `scope_hint` if it is not empty:**
- If it names folders or packages to focus on, scan only those
- If it names folders to skip, skip them

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
- The project path it was found under, and its path relative to that path's scan root
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

### 5. Present the Scan and Confirm

Show the user, per project path: the structure overview, each detected boundary (path, type, signals, confidence), the §4 catalogs (manifests, entry points, service configurations), and the scope applied (`scope_hint`, or "Full project scan"). Then display:

"Anything to rescan, investigate further or skip? Tell me, or **Select:** [C] Continue to Unit Identification | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: go to §6
- IF X: HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `scan-project:5`): "Cancelled at the project scan."
- IF Any other: rescan or skip as directed, show what changed, then [Redisplay Menu Options](#5-present-the-scan-and-confirm)

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: continue with [C], and record that decision the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "scan-project.scan", "default_action": "C", "taken_action": "C", "reason": "headless: auto-continue past scan results", "evidence": {"project_paths": <the project path count>, "boundaries": <the boundary count>}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost.

### 6. Append to Report and Continue

Replace the placeholder `[Appended by scan-project]` in {outputFile} with the scan results: the structure overview, the detected boundaries table, the manifests, entry points and service configurations catalogs, and the scope notes, grouped by project path when there are several. Update its frontmatter:

```yaml
stepsCompleted: [append 'scan-project' to existing array]
lastStep: 'scan-project'
scan_roots: {each project path: its scan root}
```

Then load, read the entire file, then execute {nextStepFile}.

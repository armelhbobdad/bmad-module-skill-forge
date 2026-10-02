---
nextStepFile: 'identify-units.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: 'references/unit-detection-heuristics.md'
scanRootFile: 'references/scan-root.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Scan Project

## STEP GOAL:

To map each project path's structure from its file list, its package manifests and its workspace layout, which the helpers read, and to list the candidate boundaries that subsequent steps use for unit identification.

## Rules

- Focus only on structural scanning — do not classify units or map exports yet
- Read no file contents: the helpers read the manifests

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
- `scope_hint`: the folders or packages to focus on or skip (may be empty)

Load {heuristicsFile} for reference on detection signals.

### 2. Scan Directory Structure

**Resolve `{scanManifestsHelper}`** from `{scanManifestsProbeOrder}` and **`{detectWorkspacesHelper}`** from `{detectWorkspacesProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `scan-project:2`): "`{the missing script}` is missing. Re-install SKF."

**The scan root of each project path.** Every helper from here on reads a local folder, the path's **scan root**, which §6 records in `scan_roots` so the later steps read the same files. Load {scanRootFile} and make the scan root of each entry of `project_paths[]` as it says. If a command there fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `scan-project:2`, path `{path}`): "{path} could not be fetched: {the first stderr line}."

**For each path in `project_paths[]`**, the `{i}`-th, scan its scan root with the helpers, never by walking its tree yourself (aggregate the results across all repos, grouped by project path):

1. List its files once. For a scan root inside a git work tree (`git -C "{scan_root}" rev-parse --is-inside-work-tree` prints `true`) run the first command, which lists the tracked files and the untracked ones git does not ignore, as `skf-disqualify-candidates.py` lists a boundary's files. Run the second for any other folder, and when the first fails or writes an empty file (a folder that an outer work tree ignores). If neither lists a file, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `scan-project:2`, path `{path}`): "The files of {path} could not be listed: {the first stderr line}."

   ```bash
   git -C "{scan_root}" -c core.quotePath=false ls-files --cached --others --exclude-standard > "{run_dir}/tree-{i}.txt"
   (cd "{scan_root}" && find . -type f -not -path '*/.git/*' | sed 's#^\./##') > "{run_dir}/tree-{i}.txt"
   ```

2. Take the structure overview and the workspace layout from the tree snapshot, which counts the listing so you never do:

   ```bash
   uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree-{i}.txt" --manifest-dir "{scan_root}" --snapshot > "{run_dir}/snapshot-{i}.json"
   ```

   It holds `file_count`, `dir_count`, `top_level_files`, `top_level_dirs`, the workspace layout (`manifest_kind`) and its `workspaces` (`{name, path, manifest}` each), and `warnings`.
3. Enumerate the package manifests and the candidate boundaries, with the snapshot's workspaces:

   ```bash
   uv run {scanManifestsHelper} scan "{scan_root}" --workspaces-file "{run_dir}/snapshot-{i}.json" > "{run_dir}/manifests-{i}.json"
   ```

   The envelope holds `manifests[]` (npm/python/rust/go/maven/gradle/ruby/composer/swift, each with its `path` and `ecosystem`, for the §4 catalog), `monorepo`, `services[]` (each Docker, compose or serverless file, for the §4 catalog: a presence check, no parsing), `candidates[]` (§3) and `warnings`.

Keep, per project path, `{path, ref, scan_root}`, the snapshot's structure overview and the scan's `manifests[]`, `services[]`, `candidates[]`, `monorepo` and `warnings`: §3 to §6 read them.

### 3. Detect Service Boundaries

Each project path's candidate boundaries are its scan's `candidates[]` ({heuristicsFile}'s **Candidate Boundaries**). When `scope_hint` is not empty, keep only the candidates inside the folders or packages it focuses on, and drop those inside the folders it skips. A candidate's signals are reported, never judged: an independent package manifest (its `manifests`), a Docker or service definition (its `services`) and workspace membership (its `workspace_member`). Judge only each candidate's boundary type and confidence.

**Document each detected boundary with:**
- The project path it was found under, and its path relative to that path's scan root
- Boundary type (service / package / module)
- Detection signals found (list specific files)
- Confidence level (strong / moderate / weak)

### 4. Catalog Manifests and Service Configurations

Create a structured catalog:

**Manifests found:**
| Path | Type | Language Indicator |
|------|------|-------------------|
| {path} | {manifest_type} | {language} |

**Service configurations found:**
| Path | Type |
|------|------|
| {path} | {config_type} |

### 5. Present the Scan and Confirm

Show the user, per project path: the structure overview, each detected boundary (path, type, signals, confidence), the §4 catalogs (manifests, service configurations), and the scope applied (`scope_hint`, or "Full project scan"). Then display:

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

Replace the placeholder `[Appended by scan-project]` in {outputFile} with the scan results: the structure overview, the detected boundaries table, the manifests and service configurations catalogs, and the scope notes, grouped by project path when there are several. Update its frontmatter:

```yaml
stepsCompleted: [append 'scan-project' to existing array]
lastStep: 'scan-project'
scan_roots: {each project path: its scan root}
```

Then load, read the entire file, then execute {nextStepFile}.

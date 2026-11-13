---
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
shapeDetectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shape-detect.py'
  - '{project-root}/src/shared/scripts/skf-shape-detect.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a §4a: Split a Monorepo into N Skills

Loaded by `step-auto-scope.md` §3b only when its cohesion check decided to **split** a monorepo (members independently published with distinct surfaces, and no umbrella re-exporting them). It replaces §4, §5 and §6 for a repo that produces N > 1 skills, then returns to §7 with the N boundaries. `{run_dir}`, `{scan_root}`, `{pinned_ref}`, `{coexistence_suffix}`, `intent_hint`, `scope_hint` and the §2 records carry into it.

## MANDATORY SEQUENCE

Every HARD HALT in this file names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "auto"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`, **`{detectLanguageHelper}`** from `{detectLanguageProbeOrder}` and **`{shapeDetectHelper}`** from `{shapeDetectProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope-split:0`): "`{the missing script}` is missing. Re-install SKF."

### 4a. Decompose by Workspace Package

Each workspace package of the §2 manifest scan with its own manifest is a candidate boundary, the scan root's own package (boundary path `.`) too when its manifest is not `private` and the scan's `candidates[]` lists `.` (code of its own beside the workspace, as a Cargo root `[package]` holds), less a member outside the folders `scope_hint` focuses on or under a folder it skips. For candidate `{c}`, list its files (every file for the scan root's package) and classify it from its own manifest and files:

```bash
awk -v p="<boundary path>/" 'p == "./" || index($0, p) == 1' "{run_dir}/tree.txt" > "{run_dir}/tree-{c}.txt"
uv run {shapeDetectHelper} --repo-url "{project_path}" --manifests-file "{run_dir}/manifests-1.json" --manifest-dir "{scan_root}" --member "<boundary path>" --tree-file "{run_dir}/tree-{c}.txt"
```

- **Exit 2:** when `tree-{c}.txt` is empty (git tracks none of the member's files: an untracked or submodule folder), a trivial member; leave it out. Otherwise HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope-split:4a`): "Shape detection failed for <boundary path>: {the `error` its stderr JSON names}."
- **`source_file_count` 0** (on exit 0 or 1): no file in a language `skf-detect-language.py` reads: a trivial member, or one whose code is all `.vue`, `.svelte`, C or another language it does not read; leave it out and record it as a warning, so it reaches the envelope: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'split: <boundary path> left out: no source file in a language SKF detects'` (if the command fails, go on).
- **Exit 0:** `{scope_type}` ← its `scope_type`. When its `signals` hold `app_or_library:framework_dep` or `language_or_user:parser_dep`, judge and record it as step-auto-scope.md §4 does, from the boundary manifest's `description` or its folder's README (a remote fetch brings it in with `git -C "{scan_root}" sparse-checkout add '/<boundary path>/README*'`), with the boundary path in the `reason`: the case you choose sets this boundary's shape, never the run's `{shape}`, and when it changes that shape, its `{scope_type}` is the type the case's row gives.
- **Exit 1** (no shape, but source files): `{scope_type}` ← `full-library`, with shape `unknown`.

Each kept boundary's `shape`, `confidence`, `export_count`, `package_count` and `{scope_type}` feed §6a and its §7 `confirmed_units` entry. Name the kept boundaries in one call to the helper that names every brief, one entry per boundary with its manifest `name` and `private` from §2:

```bash
uv run {skillInventoryHelper} derive-name --from - --skills-folder "{skills_output_folder}" <<'SKF_BOUNDARY_NAMES'
[{"target": "<boundary path>", "manifest_name": "<its manifest name>", "private": <its private flag>}, ...]
SKF_BOUNDARY_NAMES
```

Each boundary's skill name is its `names[].name`: boundaries whose names would clash are already told apart by their parent folders, and the entries `unnamed` and `duplicates` list take a name you give them from their folder. A name whose `existing` is not null belongs to a skill from another source (§0c already offered the ones from this repository): give that boundary the `-wiki` suffix, as [A]longside does, and record it as a warning, so it reaches the envelope:

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'coexistence: {name} exists, forging {name}-wiki alongside'
```

(a single quote in the name written as a backtick; if the command fails, go on). Then append `{coexistence_suffix}` to every name that does not already end with it, when it is non-empty.

### 5a. Generate Multi-Scope Patterns

For boundary `{i}`, detect its language from `tree-{c}.txt`, the file list §4a wrote for it as candidate `{c}`, without `--workspace-signal` (the workspace root's language would answer for every boundary) and read it as §5 says, the boundary's own manifest standing for the scan-root manifest. Its include and exclude patterns are the ones `scope-patterns` prints for that language, rooted at the boundary's source folder (`packages/auth/src/**/*.ts`); the scan root's package, which lists every file, also excludes `<path>/**` for each other kept boundary:

```bash
uv run {detectLanguageHelper} --tree-file "{run_dir}/tree-{c}.txt"
uv run {detectLanguageHelper} scope-patterns --tree-file "{run_dir}/tree-{c}.txt" --language <its language>
```

### 6a. Build Multi-Scope

This is the one statement of what each boundary's brief holds; §8 writes these values and the ones every brief shares (version, `source_repo`, `forge_tier`, `created`, `created_by` and the §0b pin: the pin targets a repo-level ref, not a package-level version). For boundary `{i}` of `{N}`:

- **Name:** the one §4a gave it, suffix included.
- **Scope:** `scope.type` ← its §4a `{scope_type}`, `scope.include` and `scope.exclude` from §5a, and `scope.notes` ← `Decomposed from {project_name} ({N} skills): boundary {i}/{N}, {boundary role}.`, where `{boundary role}` says in a few words what the boundary is for (for example `core library` or `CLI`).
- **Language:** the one §5a detected.
- **Description:** one to three sentences naming the parent project and the boundary's role (for example "Core library package of the my-monorepo project, providing..."), worded toward `intent_hint` when it is not empty.

### 7. The Decomposition Report

§7 writes `decomposition` into the frontmatter and appends this body in place of the single-scope section:

```markdown
## Auto-Scope Analysis: Decomposition ({N} skills)

**Mode:** auto
**Decomposition:** {reason} ({N} boundaries)
**Parent Shape:** {shape} (confidence: {confidence})
**Export Count:** {export_count}
**Package Count:** {package_count}

### Boundary 1: {boundary_name}
**Scope Type:** {scope_type}
**Boundary Path:** {boundary_path}
**Include Patterns:** {include patterns}
**Exclude Patterns:** {exclude patterns}
**Rationale:** {boundary_rationale}

### Boundary 2: {boundary_name}
...
```

After building all N scopes, return to `step-auto-scope.md` §7 with the full set of boundaries.

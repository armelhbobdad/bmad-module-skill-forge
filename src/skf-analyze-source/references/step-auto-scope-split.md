---
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
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

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}` and **`{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope-split:0`): "`{the missing script}` is missing. Re-install SKF."

### 4a. Decompose by Workspace Package

Each workspace package of the §2 manifest scan with its own manifest becomes a separate skill boundary; trivial workspace members (no source files, no exports) are excluded, and so is a member outside the folders `scope_hint` focuses on or under a folder it skips. Name the boundaries in one call to the helper that names every brief, one entry per boundary with its manifest `name` and `private` from §2:

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

**Per-boundary shape to scope mapping:** for each boundary, apply the §4 mapping independently, re-running the shape-to-scope ladder of `step-shape-detect.md` per package with each package's own manifest data. Packages may have different shapes (for example a `library-API` core and a `reference-app` CLI).

### 5a. Generate Multi-Scope Patterns

For boundary `{i}`, list its files, detect its language from them without `--workspace-signal` (the workspace root's language would answer for every boundary) and read it as §5 says, the boundary's own manifest standing for the scan-root manifest. Its include and exclude patterns are the ones `scope-patterns` prints for that language, rooted at the boundary's source folder (`packages/auth/src/**/*.ts`):

```bash
awk -v p="<boundary path>/" 'index($0, p) == 1' "{run_dir}/tree.txt" > "{run_dir}/tree-{i}.txt"
uv run {detectLanguageHelper} --tree-file "{run_dir}/tree-{i}.txt"
uv run {detectLanguageHelper} scope-patterns --tree-file "{run_dir}/tree-{i}.txt" --language <its language>
```

### 6a. Build Multi-Scope

This is the one statement of what each boundary's brief holds; §8 writes these values and the ones every brief shares (version, `source_repo`, `forge_tier`, `created`, `created_by` and the §0b pin: the pin targets a repo-level ref, not a package-level version). For boundary `{i}` of `{N}`:

- **Name:** the one §4a gave it, suffix included.
- **Scope:** `scope.type` from its §4a mapping, `scope.include` and `scope.exclude` from §5a, and `scope.notes` ← `Decomposed from {project_name} ({N} skills): boundary {i}/{N}, {boundary role}.`, where `{boundary role}` says in a few words what the boundary is for (for example `core library` or `CLI`).
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

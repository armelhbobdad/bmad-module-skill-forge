---
nextStepFile: 'health-check.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
shapeDetectScript: 'src/shared/scripts/skf-shape-detect.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a: Auto-Scope Analysis

## STEP GOAL:

To automatically scope a repo using shape detection and export surface analysis, producing a scope and skill-brief.yaml without requiring manual input. This step replaces the interactive scan-project → identify-units → map-and-detect → recommend → generate-briefs chain when `{auto_mode}` is true.

## Rules

- Auto-proceed step — no user interaction required
- This step is conditional — only loaded when `[auto]` flag is present in the pipeline context
- Must produce the same output artifacts as the interactive chain: analysis report + skill-brief.yaml
- On unknown shape (exit code 1), fall back to `scan-project.md` (the normal interactive entry point)
- On error (exit code 2), HARD HALT with exit code 3 (`resolution-failure`)

## MANDATORY SEQUENCE

### 1. Load Context

Read {outputFile} frontmatter to obtain:
- `project_paths[]` — the root(s) to analyze
- `forge_tier` — for brief generation
- `project_name`, `user_name`, `date`

Load `references/step-shape-detect.md` as reference for shape detection invocation contract and shape→scope mapping.

### 2. Manifest Scan

Perform a lightweight manifest scan — find standard package manifests in the project root and workspace paths. Do NOT crawl the full directory tree.

**For each path in `project_paths[]`:**

1. Check the project root for: `package.json`, `pyproject.toml`, `Cargo.toml`
2. If a workspace configuration exists (e.g., `pnpm-workspace.yaml`, Cargo.toml `[workspace].members`), scan workspace member paths for additional manifests
3. Record each discovered manifest as `{path, type}` pairs

**IF no manifests found:**
- Emit fallback message: "**Auto-scope could not find any package manifests — switching to interactive mode.**"
- Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**

### 3. Invoke Shape Detection

Invoke the shape detection script with discovered manifests:

```
uv run python {shapeDetectScript} --repo-url <project_path_or_url> --manifests <comma_separated_manifest_paths>
```

Parse the JSON output: `{shape, signals, confidence, export_count, package_count}`

**Handle exit codes:**

- **Exit 0 (shape classified):** Continue to §4.
- **Exit 1 (unknown shape):** Emit fallback message: "**Auto-scope could not classify this repo — switching to interactive mode.**" Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**
- **Exit 2 (error):** HARD HALT with exit code 3 (`resolution-failure`). Emit the error envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"error","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":0,"maybe":0},"exit_code":3,"halt_reason":"resolution-failure","mode":"auto"}
  ```

### 4. Map Shape to Scope

Apply the shape→scope.type mapping:

| Shape (from skf-shape-detect.py) | scope.type | Condition |
|----------------------------------|------------|-----------|
| `library-API` | `full-library` | export_count ≤ 200 |
| `library-API` | `public-api` | export_count > 200 |
| `reference-app` | `reference-app` | — |
| `language-reference` | `full-library` | — |
| `stack-compose` | `full-library` | Single scope for now |

### 5. Generate Include/Exclude Patterns

Generate `scope.include` and `scope.exclude` arrays from the detected language and project structure.

**Detect primary language** from manifest type:
- `package.json` → TypeScript/JavaScript
- `pyproject.toml` → Python
- `Cargo.toml` → Rust
- `go.mod` → Go

**Default patterns (adjust based on actual project structure):**

| Language | Default include | Default exclude |
|----------|-----------------|-----------------|
| TypeScript/JavaScript | `['src/**/*.ts', 'src/**/*.tsx']` | `['**/*.test.ts', '**/*.spec.ts', '**/node_modules/**']` |
| Python | `['src/**/*.py']` or `['{package_name}/**/*.py']` | `['**/*_test.py', '**/test_*.py', '**/tests/**']` |
| Rust | `['src/**/*.rs']` | `['**/tests/**', '**/benches/**']` |

**Adjust for actual layout:** If the project uses a non-standard layout (e.g., `lib/` instead of `src/`, or a named package directory for Python), detect and use the actual paths. Check for the existence of common source directories (`src/`, `lib/`, `pkg/`, the package name directory) and prefer the one that exists.

### 6. Build Scope and Determine Skill Name

Build the scope object:
```yaml
scope:
  type: '{mapped_scope_type}'
  include: ['{generated_include_patterns}']
  exclude: ['{generated_exclude_patterns}']
  notes: 'Auto-scoped from shape detection (shape: {shape}, confidence: {confidence})'
```

Determine the skill name from the project name or package name (kebab-case, lowercase). Use the manifest `name` field if available, otherwise derive from the project directory name.

Detect the primary language from the manifest ecosystem:
- `npm` → `typescript` (or `javascript` if no `.ts` files in includes)
- `python` → `python`
- `rust` → `rust`

### 7. Write Analysis Report

Update {outputFile} with auto-scope results.

**Update frontmatter:**
```yaml
stepsCompleted: ['init', 'auto-scope']
lastStep: 'auto-scope'
confirmed_units:
  - name: '{skill_name}'
    shape: '{shape}'
    confidence: {confidence}
    export_count: {export_count}
    package_count: {package_count}
```

**Append body section** — replace the placeholder sections with a single auto-scope section:

```markdown
## Auto-Scope Analysis

**Mode:** auto
**Shape:** {shape} (confidence: {confidence})
**Signals:** {signals list}
**Export Count:** {export_count}
**Package Count:** {package_count}
**Resolved Scope Type:** {scope_type}
**Include Patterns:** {include patterns}
**Exclude Patterns:** {exclude patterns}
```

### 8. Write Skill Brief

Create directory `{forge_data_folder}/{skill_name}/` if it does not exist.

Write `{forge_data_folder}/{skill_name}/skill-brief.yaml` conforming to the skill-brief schema (`assets/skill-brief-schema.md`):

```yaml
name: '{skill_name}'
version: '{detected_version or 1.0.0}'
source_repo: '{project_path}'
language: '{detected_language}'
scope:
  type: '{scope_type}'
  include:
    - '{include_patterns}'
  exclude:
    - '{exclude_patterns}'
  notes: 'Auto-scoped from shape detection (shape: {shape}, confidence: {confidence})'
description: '{1-3 sentence description based on shape, language, and manifest name}'
forge_tier: '{forge_tier}'
created: '{current_date}'
created_by: '{user_name}'
```

**Version detection:** Attempt to auto-detect the source version per the version detection rules in `assets/skill-brief-schema.md`. Fall back to `1.0.0` if detection fails.

### 9. Emit Result Envelope

Emit the `SKF_ANALYZE_RESULT_JSON` envelope on stdout:

```
SKF_ANALYZE_RESULT_JSON: {"status":"success","report_path":"{outputFile_path}","brief_paths":["{brief_path}"],"unit_counts":{"confirmed":1,"skipped":0,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto"}
```

### 10. Write Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_data_folder}/analyze-source-result-latest.json`. Include the generated `skill-brief.yaml` path in `outputs` and brief count in `summary`.

If `{onCompleteCommand}` is non-empty, invoke it now with `--result-path={result_json_path}`.

### 11. Chain to Health Check

Load, read fully, then execute {nextStepFile} to run the shared workflow health check.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the analysis report has been updated, the skill-brief.yaml written and validated, the result envelope emitted, and the result contract saved will you load and read fully {nextStepFile} to begin the health check.

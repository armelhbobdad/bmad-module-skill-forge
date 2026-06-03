---
nextStepFile: 'health-check.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
shapeDetectScript: 'src/shared/scripts/skf-shape-detect.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
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

### 0. URL Type Detection

Read the target URL or path from the pipeline context (`{project_path}` or the first entry in `project_paths[]`).

Apply the following heuristic to classify the input:

| Input Pattern | Classification | Route |
|---------------|---------------|-------|
| `github.com/{owner}/{repo}` (with or without `.git` suffix, with or without scheme prefix) | GitHub repo | §1 (standard auto-scope) |
| `gitlab.com/...`, `bitbucket.org/...` | Git hosting | §1 (standard auto-scope) |
| Starts with `/`, `./`, `~/`, or `~` | Local filesystem path | §1 (standard auto-scope) |
| Any other `https://` or `http://` URL | Documentation URL | §0a (docs-only) |
| Anything else (SSH URLs, `git://`, bare hostnames, etc.) | Unclassified | §1 (standard auto-scope) |

Store the classification result (documentation URL vs. repo/local/other). For all input types, continue to §0b (Pin Resolution).

### 0b. Pin Resolution

This section validates and resolves version pins. It runs for repo URLs and local paths only — skip for documentation URLs (doc URLs have no git repo to pin against). Initialize `{pinned_ref}`, `{pinned_ref_type}`, and `{pinned_version}` as null.

**For documentation URLs:** Skip this section entirely. Continue to §0c.

**For local paths when `--pin` is provided:** Emit a warning: "**Local source may not match pinned version {pin_value}.** Ensure you've checked out the correct version locally, or use a remote GitHub URL so SKF can clone from the git tag automatically." Store `{pinned_ref}` = `{pin_value}`, `{pinned_ref_type}` = `"local"`, `{pinned_version}` = `{pin_value}`. Continue to §0c without running `skf-validate-pins.py`.

**For repo URLs when `--pin` is provided:**

```bash
uv run src/shared/scripts/skf-validate-pins.py --repo-url {project_path} --pin {pin_value}
```

Handle exit codes:

- **Exit 0** (`status: "valid"`): Store `{pinned_ref}` = `resolved_ref`, `{pinned_ref_type}` = `ref_type`, `{pinned_version}` = `version`. Continue to §0c.
- **Exit 1** (`status: "invalid"`): HARD HALT with exit code 3 (`resolution-failure`). Emit error: `"Version pin '{pin_value}' not found in {project_path}. Available matches: {suggestions}. Use a valid tag, branch, or omit --pin for latest."` Emit error envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"error","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":0,"maybe":0},"exit_code":3,"halt_reason":"pin-invalid","mode":"auto"}
  ```
- **Exit 2** (error): HARD HALT with exit code 3 (`resolution-failure`). Emit error envelope with `halt_reason: "resolution-failure"`.

**For repo URLs when `--pin` is NOT provided (default):**

```bash
uv run src/shared/scripts/skf-validate-pins.py --repo-url {project_path}
```

Handle exit codes:

- **Exit 0** (`status: "resolved"`): Store `{pinned_ref}` = `resolved_ref`, `{pinned_ref_type}` = `ref_type`, `{pinned_version}` = `version`. Log: "Default pin resolved: {resolved_ref}". Continue to §0c.
- **Exit 1** (no releases found): Set `{pinned_ref}` = null, `{pinned_ref_type}` = null, `{pinned_version}` = null. Log: "No release tags found — using HEAD." Continue to §0c without pinning.
- **Exit 2**: Log warning, continue without pinning (same as exit 1 behavior).

### 0c. Coexistence Detection

This section checks for existing skills matching the target before proceeding. It runs for all input types (repo URLs, doc URLs, and local paths). Initialize `{coexistence_suffix}` as empty.

**1. Load skill inventory:**

```bash
uv run src/shared/scripts/skf-skill-inventory.py {skills_output_folder}
```

Parse the JSON output. If the exit code is non-zero or the `skills` array is empty, skip coexistence detection silently (no existing skills to conflict with) and continue to the next section: §0a for documentation URLs, §1 for all other input types.

**2. Match target against existing skills:**

For each skill in the inventory, check two match conditions (either triggers a hit):

- **URL match:** Normalize both the target URL/path and the skill's `metadata.source_repo` — strip scheme (`http://`, `https://`), strip trailing `.git`, strip trailing `/`, compare case-insensitively. A match on the normalized values is a hit.
- **Name match:** Derive the expected skill name from the target (same logic as §6 for repo URLs, §0a for doc URLs — kebab-case from the project/domain name), then compare against each skill's `name`.

**3. If zero matches:**

Complete silently. Continue to §0a for documentation URLs, §1 for all other input types. No user output.

**4. If one or more matches — coexistence gate:**

Present the user with the coexistence decision:

```
⚠️ Existing skill(s) found for {target_name}:

  • {skill_name} (v{version}) — source: {source_repo}
  [repeat for each match]

Actions:
  [A]longside — Create a new wiki skill with "-wiki" suffix (existing skill untouched)
  [M]erge     — Update the existing skill via US workflow (wiki data enriches it)
  [S]kip      — Do not create or modify any skill for this library

Choose [A/M/S]:
```

In headless mode (`{headless_mode}` is true): auto-select `[A]longside` and log: "Headless: coexistence detected for {target_name}, auto-selecting [A]longside"

**5. Handle user selection:**

- **[A]longside:** Set `{coexistence_suffix}` to `-wiki`. Continue to §0a for documentation URLs, §1 for all other input types. The existing skill is untouched.

- **[M]erge:** If multiple skills match, prompt the user to select which one to merge into before proceeding. Emit a redirect envelope signaling the forger to route to the US workflow for the selected skill:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"redirect","redirect_to":"US","skill_name":"{matched_skill_name}","skill_path":"{matched_active_path}","exit_code":0,"halt_reason":null,"mode":"auto","coexistence":"merge"}
  ```
  Write the result contract per `shared/references/output-contract-schema.md` with `status: "redirect"`.
  Chain to {nextStepFile} (health-check.md). **STOP HERE — do not proceed to §0a or §1.**

- **[S]kip:** Emit a skip envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"skipped","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":1,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto","coexistence":"skip","skipped_reason":"Existing skill for {matched_skill_name}"}
  ```
  Write the result contract with `status: "skipped"`.
  Chain to {nextStepFile} (health-check.md). **STOP HERE — do not proceed to §0a or §1.**

### 0a. Docs-Only Short-Circuit

This section handles documentation URLs that are not GitHub repos or local paths. It validates the URL, writes a minimal brief and analysis report, emits the envelope, and chains directly to health-check — skipping §1 through §11 entirely.

**1. Validate URL reachability:**

```bash
curl -sI --max-time 5 {url}
```

- On **2xx/3xx** response: URL is reachable. Continue.
- On **4xx/5xx**, DNS failure, or timeout: HARD HALT with exit code 3 (`resolution-failure`). Emit error message: `"Documentation URL unreachable: {url} — {status or error}"`. Emit error envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"error","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":0,"maybe":0},"exit_code":3,"halt_reason":"path-invalid","mode":"auto","source_type":"docs-only"}
  ```

**2. Derive skill name from URL domain:**

Extract the hostname from the URL (e.g., `docs.example.com` from `https://docs.example.com/guide/intro`), convert to kebab-case (replace `.` with `-`), yielding e.g. `docs-example-com`. If `{coexistence_suffix}` is non-empty, append it to the skill name (e.g., `docs-example-com-wiki`).

**3. Write analysis report:**

Update {outputFile} with docs-only results.

**Update frontmatter:**
```yaml
stepsCompleted: ['init', 'auto-scope']
lastStep: 'auto-scope'
source_type: docs-only
confirmed_units:
  - name: '{skill_name}'
    shape: 'docs-only'
    confidence: 1.0
    export_count: 0
    package_count: 0
```

**Append body section:**
```markdown
## Auto-Scope Analysis

**Mode:** auto (docs-only short-circuit)
**Source Type:** docs-only
**Documentation URL:** {url}
**Skill Name:** {skill_name}
```

**4. Write skill brief via canonical writer:**

Create directory `{forge_data_folder}/{skill_name}/` if it does not exist.

Write `{forge_data_folder}/{skill_name}/skill-brief.yaml` through the canonical writer (`skf-write-skill-brief.py`) with the following context:

```json
{
  "name":             "{skill_name}",
  "target_version":   null,
  "detected_version": null,
  "source_type":      "docs-only",
  "source_repo":      "{url}",
  "language":         "",
  "description":      "Skill created from documentation at {url}",
  "forge_tier":       "{forge_tier}",
  "created":          "{current_date}",
  "created_by":       "{user_name}",
  "scope_type":       "docs-only",
  "scope_include":    [],
  "scope_exclude":    [],
  "scope_notes":      "Docs-only skill created from documentation URL",
  "scope_rationale":  null,
  "scope_tier_a_include": null,
  "scope_amendments":     null,
  "doc_urls":         [{"url": "{url}", "label": "Primary Documentation"}],
  "scripts_intent":   null,
  "assets_intent":    null,
  "source_authority": "community",
  "target_ref":       null,
  "source_ref":       null,
  "version_resolved": "1.0.0"
}
```

**5. Emit success envelope:**

```
SKF_ANALYZE_RESULT_JSON: {"status":"success","report_path":"{outputFile_path}","brief_paths":["{brief_path}"],"unit_counts":{"confirmed":1,"skipped":0,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto","source_type":"docs-only"}
```

If `{coexistence_suffix}` is non-empty (i.e., [A]longside was selected in §0c), include `"coexistence":"alongside"` in the envelope.

The `source_type` field signals downstream consumers (BS) to skip repo-based enrichment.

**6. Write result contract** per `shared/references/output-contract-schema.md`: the per-run record and latest copy, same as §10.

If `{onCompleteCommand}` is non-empty, invoke it now with `--result-path={result_json_path}`.

**7. Chain to health check:**

Load, read fully, then execute {nextStepFile} to run the shared workflow health check. **Skip §1 through §11 entirely.**

### 1. Load Context

Read {outputFile} frontmatter to obtain:
- `project_paths[]` — the root(s) to analyze
- `forge_tier` — for brief generation
- `project_name`, `user_name`, `date`

Load `references/step-shape-detect.md` as reference for shape detection invocation contract and shape→scope mapping.

### 2. Manifest Scan

Enumerate package manifests **deterministically** via `{scanManifestsHelper}` (the same helper the interactive `scan-project.md` uses) — do not hand-scan. Resolve `{scanManifestsHelper}` as the first path in `{scanManifestsProbeOrder}` that exists. The scanner reads a **local directory**, so how you point it at the target depends on the input form classified in §0:

**For each path in `project_paths[]`:**

- **Local filesystem path** (starts with `/`, `./`, `~/`, `~`, or is an existing directory) — scan it directly:

  ```bash
  uv run {scanManifestsHelper} scan {path}
  ```

- **Remote git URL** (e.g. `github.com/{owner}/{repo}`) — auto-scope has no working tree yet and the scanner cannot read a URL. Fetch **just the manifests** first (blobless + sparse + depth-1 — no source blobs, typically KB–MB even for large monorepos), then scan that tree:

  ```bash
  tmp="$(mktemp -d)"
  git clone --filter=blob:none --no-checkout --depth 1 {pinned_branch_flag} {path} "$tmp"
  git -C "$tmp" sparse-checkout set --no-cone '**/package.json' '**/Cargo.toml' '**/pyproject.toml' '**/go.mod' 'pnpm-workspace.yaml' '**/pnpm-workspace.yaml'
  git -C "$tmp" checkout
  uv run {scanManifestsHelper} scan "$tmp"
  ```

  where `{pinned_branch_flag}` is `--branch {pinned_ref}` when a pin was resolved in §0b (so manifests match the target version), otherwise omitted. **Retain `"$tmp"` through §3** — shape detection reads the discovered manifest files from it — then it may be discarded.

Parse the JSON envelope: `{manifests: [{path, ecosystem, ...}], total_unique, monorepo, warnings?}`. The scanner discovers the project root plus monorepo workspace members (npm/pnpm/yarn `workspaces`, Cargo `[workspace]`, and other ecosystems) and sets the `monorepo` flag — so members are found without hand-listing each workspace convention, for both local trees and remote fetches.

From the envelope, record:

1. **Supported manifest paths** — filter `manifests[].path` to the types `skf-shape-detect.py` accepts (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`). Each `manifests[].path` is **relative to the scan root**, so resolve them against that root (`{path}` for a local scan, `"$tmp"` for a remote fetch) before use. This filtered, comma-joined list of resolved paths is fed to shape detection in §3. For a monorepo, it includes each workspace member's manifest, so the package surface is classified accurately rather than from a bare (and often export-less) repo root. The scanner also discovers ecosystems shape detection does not yet classify (e.g. Maven, Gradle); those are excluded here, so a repo with no supported manifest falls back to interactive at the next check rather than auto-scoping.
2. **`monorepo` flag** and the count of discovered supported packages — carried forward as a signal for the decomposition decision in §3a.

**IF no supported manifests are found** (the filtered list is empty):
- Emit fallback message: "**Auto-scope could not find any supported package manifests — switching to interactive mode.**"
- Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**

### 3. Invoke Shape Detection

Invoke the shape detection script with discovered manifests:

```
uv run {shapeDetectScript} --repo-url <project_path_or_url> --manifests <comma_separated_manifest_paths>
```

Parse the JSON output: `{shape, signals, confidence, export_count, package_count}`

**Handle exit codes:**

- **Exit 0 (shape classified):** Continue to §3a.
- **Exit 1 (unknown shape):** Emit fallback message: "**Auto-scope could not classify this repo — switching to interactive mode.**" Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**
- **Exit 2 (error):** HARD HALT with exit code 3 (`resolution-failure`). Emit the error envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"error","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":0,"maybe":0},"exit_code":3,"halt_reason":"resolution-failure","mode":"auto"}
  ```

### 3a. Check Decomposition Thresholds

Evaluate the shape detection output to determine whether this repo should be decomposed into multiple skills.

**Threshold conditions:**

| Threshold | Condition | Signal |
|-----------|-----------|--------|
| Large export surface | `export_count > 500` `[PENDING VALIDATION]` | Single skill covering 500+ exports produces unwieldy output (not yet observed firing on a real run) |
| Monorepo / multi-package | `package_count > 3` | 4+ packages — a decomposition **candidate** (empirically validated: fires on real 15-, 38-, and 442-package workspaces) |

**Decision:**

- **Neither threshold met** → Continue to §4 (single-scope flow, entirely unchanged).
- **Either or both thresholds met** → this repo is a **decomposition candidate**. A threshold firing means the repo *could* decompose, not that it *should* — continue to §3b to decide merge-vs-split. Log: "Auto-decomposition candidate: {reason} ({value} exceeds threshold {threshold})" where reason is `export_threshold`, `package_threshold`, or `both`.

### 3b. Cohesion Check — Merge to One Skill vs Split into N

Reached only when §3a flagged a decomposition candidate. Most published monorepos are **cohesive** and produce a better single skill than a pile of fragments — empirically, 5/5 real monorepos (animato 15 crates, trpc, react 38 packages, aws-sdk-js-v3 442 packages, plus zod) were best served as one cohesive skill or a curated few, not one-skill-per-package. Decide deliberately:

**Merge into ONE cohesive skill** (override the threshold → continue to §4 single-scope) when **any** of these hold:

- **Umbrella facade** — one package re-exports the members: a root or named package whose dependencies include the other workspace members, or which `pub use` / `export *`s them. The facade *is* the public surface (e.g. animato's `crates/animato` re-exporting its 15 sub-crates).
- **Shared runtime contract** — the members are consumed together through one entry point, and teaching the shared invariant covers them (e.g. tRPC's adapters around `@trpc/server`; aws-sdk's `new XClient(...) → client.send(new YCommand(...))` shared by every `@aws-sdk/client-*`).
- **Internal building blocks** — the members are private/internal pieces of one product, not independently meaningful to a consumer.

**Split into N skills** (→ §4a) when:

- The members are **independently published with distinct public surfaces serving different concerns**, **and no umbrella re-exports them** — e.g. `react-dom` and `react-server-dom-*` are separate installs with separate jobs, or a federated SDK where a consumer only ever wants one service. Each genuinely-distinct facet earns its own skill.

If genuinely unsure, **prefer merge** — a too-broad single skill is recoverable with `US`; N fragmented skills are not.

**Facet-coverage guard (merged facet-diverse repos only).** When you merge a repo whose members have genuinely distinct surfaces and you scope to only some of them, record the decision explicitly — never drop a facet silently:

- In `scope.notes`, name the in-scope facets **and** the excluded major facets, e.g. _"Scoped to react + react-dom core; excludes react-server-dom-\* (RSC), the specialized renderers (react-art/native/test), and the compiler — forge a separate skill for those."_
- Surface the excluded facets in the analysis report (§7) so the operator can re-scope or forge a companion skill.

### 4. Map Shape to Scope

Apply the shape→scope.type mapping:

| Shape (from skf-shape-detect.py) | scope.type | Condition |
|----------------------------------|------------|-----------|
| `library-API` | `full-library` | export_count ≤ 200 |
| `library-API` | `public-api` | export_count > 200 |
| `reference-app` | `reference-app` | — |
| `language-reference` | `full-library` | — |
| `stack-compose` | `full-library` | Decomposition candidate when `package_count > 3` — cohesion-checked at §3b |

### 5. Generate Include/Exclude Patterns

Generate `scope.include` and `scope.exclude` arrays from the detected language and project structure.

**Detect primary language** from manifest type (the same set shape detection classifies):
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
| Go | `['**/*.go']` | `['**/*_test.go', '**/vendor/**']` |

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

Determine the skill name from the project name or package name (kebab-case, lowercase). Use the manifest `name` field if available, otherwise derive from the project directory name. If `{coexistence_suffix}` is non-empty, append it to the skill name.

Detect the primary language from the manifest ecosystem:
- `npm` → `typescript` (or `javascript` if no `.ts` files in includes)
- `python` → `python`
- `rust` → `rust`
- `go` → `go`

### 4a. Multi-Scope Decomposition

This section is reached only from §3b when the cohesion check decided to **split** (members are independently published with distinct surfaces and no umbrella re-exports them). It replaces §4→§5→§6 for repos that will produce N > 1 skills.

**Determine decomposition path:**

- **Monorepo path** (`package_count > 3`): Use workspace package discovery from §2 manifest scan results. Each workspace package with its own manifest becomes a separate skill boundary. Name each skill as `{project_name}-{package_name}` (kebab-case); if `{coexistence_suffix}` is non-empty, append it. Trivial workspace members (no source files, no exports) are excluded.
- **Large-export path** (`export_count > 500`, single package): Group by top-level source directory modules (e.g., `src/auth/`, `src/core/`, `src/api/`). Each directory subtree with a meaningful export surface becomes a separate skill boundary. Candidate boundaries with fewer than ~50 exports `[PENDING VALIDATION]` should be merged into an "other" catch-all skill rather than becoming standalone skills. Name each skill as `{project_name}-{module_name}` (kebab-case); if `{coexistence_suffix}` is non-empty, append it. If no clear module structure exists (flat `src/` with all files at root level), **do not force decomposition** — fall back to single-scope flow at §4.
- **Combined path** (both thresholds met): Use the monorepo path. Package boundaries are explicit and take priority over export-count grouping (which is heuristic).

**Per-boundary shape→scope mapping:**

For each decomposed boundary, apply the shape→scope mapping from §4 independently — the boundary's local characteristics determine its scope.type:

| Decomposition Type | Per-Boundary Shape Mapping |
|--------------------|---------------------------|
| Monorepo (`package_count > 3`) | Re-run the shape→scope heuristic ladder from `step-shape-detect.md` per package using each package's own manifest data. Packages may have different shapes (e.g., a `library-API` core + a `reference-app` CLI). |
| Large-export (`export_count > 500`) | All boundaries inherit the parent shape. scope.type varies by per-boundary export count (e.g., ≤200 → `full-library`, >200 → `public-api`). |

### 5a. Generate Multi-Scope Patterns

For each decomposed boundary, generate include/exclude patterns using the same language-aware rules as §5, but scoped to the boundary's source paths.

- Monorepo boundaries: patterns are rooted at the package path (e.g., `packages/auth/src/**/*.ts` instead of `src/**/*.ts`)
- Large-export boundaries: patterns are rooted at the module directory (e.g., `src/auth/**/*.ts`)

### 6a. Build Multi-Scope

For each boundary, build a scope object following the same structure as §6.

Include decomposition metadata in `scope.notes`: "Decomposed from {project_name} — boundary {i}/{N} ({reason})"

Determine each boundary's skill name from the boundary-derived name (kebab-case, lowercase). If `{coexistence_suffix}` is non-empty, append it to each skill name. Detect the primary language from each boundary's manifest ecosystem (same rules as §6).

**Pin data (from §0b):** All N decomposed briefs share the same pin — the pin targets a repo-level ref, not a package-level version. Apply the same `target_version`/`target_ref` values from §0b to all N boundaries at brief write time (§8).

After building all N scopes, continue to §7 with the full set of boundaries.

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
    boundary_path: '{boundary_path}'  # present only for decomposed units
  # ... N entries when decomposition is active
```

**When decomposition was triggered (N > 1 units):**

Add `decomposition` to frontmatter:
```yaml
decomposition:
  triggered: true
  reason: 'export_threshold' | 'package_threshold' | 'both'
  boundary_count: N
```

Each `confirmed_units` entry includes `boundary_path` — the relative path to the boundary's root (e.g., `packages/core` for monorepo, `src/auth` for large-export). Omit the `decomposition` key entirely when single-scope (N = 1).

**When single-scope (N = 1):** No `decomposition` key. `confirmed_units` contains a single entry (existing behavior).

**Append body section:**

For single-scope (unchanged):
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

For multi-scope (N > 1):
```markdown
## Auto-Scope Analysis — Decomposition ({N} skills)

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

### 8. Write Skill Brief

**For each confirmed unit** (1 for single-scope, N for decomposition):

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

**When decomposition is active (N > 1 units):**

Loop over all N boundaries. For each boundary:
- `name` is the boundary-derived skill name (e.g., `my-monorepo-core`)
- `include`/`exclude` patterns are boundary-scoped (from §5a)
- `scope.notes` includes decomposition context: "Decomposed from {project_name} ({N} skills) — boundary {i}/{N}: {boundary_description}"
- `description` references the parent project and boundary role (e.g., "Core library package of the my-monorepo project, providing...")
- All N briefs share the same `version`, `source_repo`, `language`, `forge_tier`, `created`, `created_by` values as the parent project

**Version detection:** Attempt to auto-detect the source version per the version detection rules in `assets/skill-brief-schema.md`. Fall back to `1.0.0` if detection fails.

**Pin data (from §0b):** When `{pinned_ref}` is non-null, enrich the brief with pin data:

- If `{pinned_ref_type}` is `"tag"`: set `target_version` = `{pinned_version}`, `target_ref` = `{pinned_ref}`, `version` = `{pinned_version}`.
- If `{pinned_ref_type}` is `"branch"`: set `target_ref` = `{pinned_ref}`, leave `target_version` = null, `version` = auto-detected or `1.0.0`.
- If `{pinned_ref_type}` is `"local"`: set `target_version` = `{pinned_version}`, `target_ref` = null, `version` = `{pinned_version}`.

When `{pinned_ref}` is null (no pin, no releases): leave `target_version` = null, `target_ref` = null — existing version detection applies unchanged.

In the docs-only path (§0a), `--pin` is ignored (already skipped at §0b). No changes to §0a.

### 9. Emit Result Envelope

Emit the `SKF_ANALYZE_RESULT_JSON` envelope on stdout:

```
SKF_ANALYZE_RESULT_JSON: {"status":"success","report_path":"{outputFile_path}","brief_paths":["{brief_path_1}","{brief_path_2}",...,"{brief_path_N}"],"unit_counts":{"confirmed":N,"skipped":0,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto"}
```

`brief_paths` contains N paths (one per confirmed unit). `unit_counts.confirmed` is N. The envelope JSON format is structurally unchanged — `brief_paths` was already an array and `unit_counts.confirmed` was already a number. No breaking change for downstream consumers.

If `{coexistence_suffix}` is non-empty (i.e., [A]longside was selected in §0c), include `"coexistence":"alongside"` in the envelope.

When `{pinned_ref}` is non-null, include `"pinned_ref":"{pinned_ref}"` and `"pinned_version":"{pinned_version}"` in the envelope. These flow downstream to BS/CS for provenance recording. When `{pinned_ref}` is null, omit these fields (backward-compatible — existing consumers don't expect them).

### 10. Write Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_data_folder}/analyze-source-result-latest.json`. `outputs` lists all N brief paths and `summary` includes the brief count N.

If `{onCompleteCommand}` is non-empty, invoke it now with `--result-path={result_json_path}`.

### 11. Chain to Health Check

Load, read fully, then execute {nextStepFile} to run the shared workflow health check.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the analysis report has been updated, the skill-brief.yaml written and validated, the result envelope emitted, and the result contract saved will you load and read fully {nextStepFile} to begin the health check.

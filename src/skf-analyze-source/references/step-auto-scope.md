---
nextStepFile: 'health-check.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
shapeDetectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shape-detect.py'
  - '{project-root}/src/shared/scripts/skf-shape-detect.py'
validatePinsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-pins.py'
  - '{project-root}/src/shared/scripts/skf-validate-pins.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
languageCorporaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-language-corpora.py'
  - '{project-root}/src/shared/scripts/skf-language-corpora.py'
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

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If neither resolves, HARD HALT with exit code 3 (`resolution-failure`) and the error envelope on stderr (shape in `references/headless-contract.md`). The helper that names every brief classifies the target:

```bash
uv run {skillInventoryHelper} derive-name --target "{project_path}"
```

| Input | Classification | Route |
|-------|----------------|-------|
| `basis` is `docs-host` | Documentation URL | `references/auto-docs-only.md` (docs-only, via §0c) |
| Starts with `/`, `./`, `~/`, or `~` | Local filesystem path | §1 (standard auto-scope) |
| Anything else (a git host URL, an SSH URL, `git://`, a bare hostname) | Repo URL | §1 (standard auto-scope) |

Store the classification result (documentation URL vs. repo/local/other). For all input types, continue to §0b (Pin Resolution).

### 0b. Pin Resolution

This section validates and resolves version pins. It runs for repo URLs and local paths only — skip for documentation URLs (doc URLs have no git repo to pin against). Initialize `{pinned_ref}`, `{pinned_ref_type}`, and `{pinned_version}` as null.

**For documentation URLs:** Skip this section entirely. Continue to §0c.

**For local paths when `--pin` is provided:** Emit a warning: "**Local source may not match pinned version {pin_value}.** Ensure you've checked out the correct version locally, or use a remote GitHub URL so SKF can clone from the git tag automatically." Store `{pinned_ref}` = `{pin_value}`, `{pinned_ref_type}` = `"local"`, `{pinned_version}` = `{pin_value}`. Continue to §0c without running `skf-validate-pins.py`.

**For repo URLs when `--pin` is provided:**

**Resolve `{validatePinsHelper}`** from `{validatePinsProbeOrder}`; first existing path wins; HALT if neither resolves.

```bash
uv run {validatePinsHelper} --repo-url {project_path} --pin {pin_value}
```

Handle exit codes:

- **Exit 0** (`status: "valid"`): Store `{pinned_ref}` = `resolved_ref`, `{pinned_ref_type}` = `ref_type`, `{pinned_version}` = `version`. Continue to §0c.
- **Exit 1** (`status: "invalid"`): HARD HALT with exit code 3 (`resolution-failure`). Emit error: `"Version pin '{pin_value}' not found in {project_path}. Available matches: {suggestions}. Use a valid tag, branch, or omit --pin for latest."` Emit the error envelope (shape in `references/headless-contract.md`) with `exit_code: 3`, `halt_reason: "pin-invalid"`, `mode: "auto"`.
- **Exit 2** (error): HARD HALT with exit code 3 (`resolution-failure`). Emit the error envelope with `halt_reason: "resolution-failure"`.

**For repo URLs when `--pin` is not provided (default):**

Using the same `{validatePinsHelper}` resolved above:

```bash
uv run {validatePinsHelper} --repo-url {project_path}
```

Handle exit codes:

- **Exit 0** (`status: "resolved"`): Store `{pinned_ref}` = `resolved_ref`, `{pinned_ref_type}` = `ref_type`, `{pinned_version}` = `version`. Log: "Default pin resolved: {resolved_ref}". Continue to §0c.
- **Exit 1** (no releases found): Set `{pinned_ref}` = null, `{pinned_ref_type}` = null, `{pinned_version}` = null. Log: "No release tags found — using HEAD." Continue to §0c without pinning.
- **Exit 2**: Log warning, continue without pinning (same as exit 1 behavior).

### 0c. Coexistence Detection

This section checks for existing skills matching the target before proceeding. It runs for all input types (repo URLs, doc URLs, and local paths). Initialize `{coexistence_suffix}` as empty.

**1. Load skill inventory:**

Pass the target (`{project_path}`) to `{skillInventoryHelper}`, resolved in §0, so the helper computes the coexistence match set for you; do not re-match by hand:

```bash
uv run {skillInventoryHelper} "{skills_output_folder}" --match-target "{project_path}"
```

Parse the JSON output. If the exit code is non-zero or the `skills` array is empty, skip coexistence detection silently (no existing skills to conflict with) and continue: load, read fully, then execute `references/auto-docs-only.md` for documentation URLs; §1 for all other input types.

**2. Read the match set:**

Read the top-level **`matches[]`** array; the helper has already matched, so do not re-match. Each entry is:

```json
{ "name": "...", "active_version": "...", "source_repo": "...", "active_path": "...", "match_reason": "url" | "name" | "both", "skf_skill": true | false }
```

`skf_skill` is true when SKF generated the matched skill (its `metadata.json` carries an SKF marker). Only those are offered for a merge: a merge hands the skill to update-skill, which rewrites its files, and SKF changes only the skills it generated.

**3. If `matches[]` is empty:**

Complete silently. Continue: execute `references/auto-docs-only.md` for documentation URLs; §1 for all other input types. No user output.

**4. If `matches[]` has one or more entries — coexistence gate:**

Present the user with the coexistence decision, one bullet per `matches[]` entry (`{skill_name}` = `matches[].name`, `{version}` = `matches[].active_version`, `{source_repo}` = `matches[].source_repo`). Append " — not SKF output, merge not offered" to the bullet of every entry whose `matches[].skf_skill` is false, and leave the `[M]erge` line out when no entry has `matches[].skf_skill` true:

```
⚠️ Existing skill(s) found for {target_name}:

  • {skill_name} (v{version}) — source: {source_repo}
  [repeat for each entry in matches[]]

Actions:
  [A]longside — Create a new wiki skill with "-wiki" suffix (existing skill untouched)
  [M]erge     — Update the existing skill via US workflow (wiki data enriches it; SKF-generated skills only)
  [S]kip      — Do not create or modify any skill for this library

Choose [A/M/S]:
```

In headless mode (`{headless_mode}` is true): auto-select `[A]longside` and log: "Headless: coexistence detected for {target_name}, auto-selecting [A]longside"

**5. Handle user selection:**

- **[A]longside:** Set `{coexistence_suffix}` to `-wiki`. Continue: execute `references/auto-docs-only.md` for documentation URLs; §1 for all other input types. The existing skill is untouched.

- **[M]erge:** Offered only for entries whose `matches[].skf_skill` is true. If more than one such entry exists, prompt the user to select which one to merge into before proceeding. Read `{matched_skill_name}` = the selected entry's `matches[].name` and `{matched_active_path}` = its `matches[].active_path`. Emit a redirect envelope signaling the forger to route to the US workflow for the selected skill:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"redirect","redirect_to":"US","skill_name":"{matched_skill_name}","skill_path":"{matched_active_path}","exit_code":0,"halt_reason":null,"mode":"auto","coexistence":"merge"}
  ```
  Write the result contract per `shared/references/output-contract-schema.md` with `status: "redirect"`.
  Chain to {nextStepFile} (health-check.md). **STOP HERE — do not proceed to the docs-only sub-flow or §1.**

- **[S]kip:** Emit a skip envelope:
  ```
  SKF_ANALYZE_RESULT_JSON: {"status":"skipped","report_path":null,"brief_paths":[],"unit_counts":{"confirmed":0,"skipped":1,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto","coexistence":"skip","skipped_reason":"Existing skill for {matched_skill_name}"}
  ```
  Write the result contract with `status: "skipped"`.
  Chain to {nextStepFile} (health-check.md). **STOP HERE — do not proceed to the docs-only sub-flow or §1.**

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
  git -C "$tmp" sparse-checkout set --no-cone '**/package.json' '**/Cargo.toml' '**/pyproject.toml' '**/go.mod' '**/pom.xml' '**/build.gradle' '**/build.gradle.kts' '**/Package.swift' 'pnpm-workspace.yaml' '**/pnpm-workspace.yaml'
  git -C "$tmp" checkout
  uv run {scanManifestsHelper} scan "$tmp"
  ```

  where `{pinned_branch_flag}` is `--branch {pinned_ref}` when a pin was resolved in §0b (so manifests match the target version), otherwise omitted. **Retain `"$tmp"` through §3** — shape detection reads the discovered manifest files from it — then it may be discarded.

Parse the JSON envelope: `{manifests: [{path, ecosystem, ...}], total_unique, monorepo, warnings?}`. The scanner discovers the project root plus monorepo workspace members (npm/pnpm/yarn `workspaces`, Cargo `[workspace]`, and other ecosystems) and sets the `monorepo` flag — so members are found without hand-listing each workspace convention, for both local trees and remote fetches.

From the envelope, record:

1. **Supported manifest paths** — filter `manifests[].path` to the types `skf-shape-detect.py` accepts (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Package.swift`). Each `manifests[].path` is **relative to the scan root**, so resolve them against that root (`{path}` for a local scan, `"$tmp"` for a remote fetch) before use. This filtered, comma-joined list of resolved paths is fed to shape detection in §3. For a monorepo, it includes each workspace member's manifest, so the package surface is classified accurately rather than from a bare (and often export-less) repo root. The scanner may discover ecosystems shape detection does not yet classify; those are excluded here, so a repo with no supported manifest falls back to interactive at the next check rather than auto-scoping.
2. **`monorepo` flag** and the count of discovered supported packages — carried forward as a signal for the decomposition decision in §3a.
3. **The names and flags §3b, §4a and §6 read:** the scan-root manifest's `name` and `private` (the `manifests[]` entry whose `path` has no folder), each member manifest's `name`, `private` and `internal_deps`, and `umbrella_candidates[]`. Read them from the envelope; never open a member manifest for them.

**Harvest tree-level language signals.** A whole-language repo may declare no parser-generator dependency (a hand-written compiler such as rustc, TypeScript, or the Go toolchain) or carry no supported manifest at all (CPython, Ruby). From the **same** fetched tree — no second clone and no blobs, since tree objects are already present in the blobless clone — collect two signals for shape detection. These are pure path listings (`git ls-tree` reads tree objects; no checkout, no blob download):

- **Remote fetch** (`"$tmp"`), or a **local path** that is a git repo (`git -C {path}`):
  ```bash
  files="$(git -C "$tmp" ls-tree -r    --name-only HEAD)"   # every file path
  dirs="$( git -C "$tmp" ls-tree -r -d --name-only HEAD)"   # every directory
  # Grammar files (depth-capped to skip deep vendored fixtures, hard-capped):
  grammar_matches="$(printf '%s\n' "$files" \
    | grep -Ei '\.(g4|pest|lalrpop|y|gram|lark|ebnf|peg|ungram)$|/grammar\.(js|json)$' \
    | awk -F/ 'NF<=4' | head -n 50 | paste -sd, -)"
  # Directory signals (trailing /) + depth-capped file basenames, narrowed to
  # compiler-relevant paths so the argument stays bounded on huge repos. The
  # filter is a loose superset of shape detection's gates — the script does the
  # precise matching; this only keeps the list small.
  tree_paths="$({ printf '%s\n' "$dirs" | sed 's#$#/#'; \
                  printf '%s\n' "$files" | awk -F/ 'NF<=5'; } \
    | grep -Ei '(^|/)(compiler|compile|syntax|scanner|lexer|tokeniz|parser|parse|ast|binder|checker|codegen|ssagen|interpreter|vm|eval|rustc_[a-z]+)' \
    | head -n 400 | paste -sd, -)"
  ```
- **Local path that is not a git repo** (`{path}`): list the tree with `find` instead, then derive `grammar_matches` / `tree_paths` the same way:
  ```bash
  files="$(cd {path} && find . -type f -not -path '*/.git/*' | sed 's#^\./##')"
  dirs="$( cd {path} && find . -type d -not -path '*/.git/*' | sed 's#^\./##')"
  ```

Record `<grammar_matches>` and `<tree_paths>` (each a comma-joined list, possibly empty) for §3.

**IF no supported manifests are found** (the filtered list is empty):
- **AND** `<grammar_matches>` is empty **AND** `<tree_paths>` shows no compiler directory (none of `compiler/`, `src/compiler/`, `cmd/compile/`, `internal/syntax/`, or a `Parser/`): the repo carries no language signal — emit fallback message: "**Auto-scope could not find any supported package manifests — switching to interactive mode.**" Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**
- **Otherwise** (a grammar file or a compiler directory is present) the repo is a manifest-less language toolchain (CPython, Ruby): proceed to §3 with an **empty** `--manifests` and the harvested `--grammar-files` / `--tree-paths`.

### 3. Invoke Shape Detection

**Resolve `{shapeDetectHelper}`** from `{shapeDetectProbeOrder}`; first existing path wins; HALT if neither resolves.

Invoke the shape detection script with the discovered manifests and the harvested tree-level signals:

```
uv run {shapeDetectHelper} --repo-url <project_path_or_url> \
  --manifests <comma_separated_manifest_paths> \
  --grammar-files <grammar_matches> --tree-paths <tree_paths>
```

`<comma_separated_manifest_paths>` may be empty for a manifest-less language repo, provided `<grammar_matches>` or `<tree_paths>` carries the signal. Parse the JSON output: `{shape, signals, confidence, export_count, package_count}`

**Handle exit codes:**

- **Exit 0 (shape classified):** Continue to §3a.
- **Exit 1 (unknown shape):** Emit fallback message: "**Auto-scope could not classify this repo — switching to interactive mode.**" Load, read fully, then execute `references/scan-project.md`. **STOP HERE.**
- **Exit 2 (error):** HARD HALT with exit code 3 (`resolution-failure`). Emit the error envelope (shape in `references/headless-contract.md`) with `exit_code: 3`, `halt_reason: "resolution-failure"`, `mode: "auto"`.

### 3a. Check Decomposition Thresholds

Evaluate the shape detection output to determine whether this **monorepo** should be decomposed into multiple skills.

Apply the **Decomposition Thresholds** ladder from `step-shape-detect.md` (loaded at §1). A *single* package with a large API surface is **not** a trigger — only a genuine multi-package monorepo is.

**Decision:**

- **Threshold not met** (`package_count ≤ 3`) → Continue to §4 (single-scope flow, entirely unchanged).
- **Threshold met** (`package_count > 3`) → this repo is a **decomposition candidate**. A threshold firing means the repo *could* decompose, not that it *should* — continue to §3b to decide merge-vs-split. Log: "Auto-decomposition candidate: package_threshold ({value} packages exceeds 3)".

### 3b. Cohesion Check — Merge to One Skill vs Split into N

Reached only when §3a flagged a decomposition candidate. Most published monorepos are **cohesive** and produce a better single skill than a pile of fragments. Load `{unitDetectionHeuristicsPath}` and apply its **Cohesion Triggers**, the one statement of when members belong in one skill, reading their evidence from the §2 envelope (`umbrella_candidates[]`, and each member's `name`, `private` and `internal_deps`) and never from the member manifests themselves. Decide deliberately:

- **Merge into ONE cohesive skill** (override the threshold → continue to §4 single-scope) when **any** cohesion trigger holds.
- **Split into N skills** (→ §4a) when the members meet its split condition instead.

If genuinely unsure, **prefer merge** — a too-broad single skill is recoverable with `US`; N fragmented skills are not.

**Facet-coverage guard (merged facet-diverse repos only).** When you merge a repo whose members have genuinely distinct surfaces and you scope to only some of them, record the decision explicitly — never drop a facet silently:

- In `scope.notes`, name the in-scope facets **and** the excluded major facets, e.g. _"Scoped to react + react-dom core; excludes react-server-dom-\* (RSC), the specialized renderers (react-art/native/test), and the compiler — forge a separate skill for those."_
- Surface the excluded facets in the analysis report (§7) so the operator can re-scope or forge a companion skill.

### 4. Map Shape to Scope

Apply the canonical **Shape → Scope Type Mapping** table from `step-shape-detect.md` (loaded at §1) — the single source of truth for this ladder (the `export_count > 200 → public-api` split, the `language-reference` corpora caveat, and the `stack-compose` decomposition note).

### 5. Generate Include/Exclude Patterns

Generate `scope.include` and `scope.exclude` arrays from the detected language and project structure.

**Detect the primary language once, deterministically**, via the shared helper — the single source of truth for the manifest→language rule table (§6b resolves the same helper; do not restate the table in prose, where it drifts from the script). **Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}` (first existing path wins). Pipe the §2 supported-manifest paths (and, for a manifest-less toolchain, the harvested `<tree_paths>`) as the file tree:

```bash
echo '{"tree": [<§2 supported manifest paths + harvested tree paths>]}' | uv run {detectLanguageHelper}
```

Read `.language` as `{detected_language}` (and `.confidence`) — the helper owns the `tsconfig.json` JS-vs-TS and `build.gradle` Java-vs-Kotlin disambiguation. §6 reuses `{detected_language}` for the brief's `language` field: detect once.

**Default patterns (adjust based on actual project structure):**

| Language | Default include | Default exclude |
|----------|-----------------|-----------------|
| TypeScript/JavaScript | `['src/**/*.ts', 'src/**/*.tsx']` | `['**/*.test.ts', '**/*.spec.ts', '**/node_modules/**']` |
| Python | `['src/**/*.py']` or `['{package_name}/**/*.py']` | `['**/*_test.py', '**/test_*.py', '**/tests/**']` |
| Rust | `['src/**/*.rs']` | `['**/tests/**', '**/benches/**']` |
| Go | `['**/*.go']` | `['**/*_test.go', '**/vendor/**']` |
| Java | `['src/main/java/**/*.java']` | `['**/src/test/**']` |
| Kotlin | `['src/main/kotlin/**/*.kt']` | `['**/src/test/**']` |
| Swift | `['Sources/**/*.swift']` | `['**/Tests/**']` |

**Adjust for actual layout:** If the project uses a non-standard layout (e.g., `lib/` instead of `src/`, or a named package directory for Python), detect and use the actual paths. Check for the existence of common source directories (`src/`, `lib/`, `pkg/`, the package name directory) and prefer the one that exists.

### 6. Build Scope and Determine Skill Name

Build the scope object:
```yaml
scope:
  type: '{mapped_scope_type}'
  include: ['{generated_include_patterns}']
  exclude: ['{generated_exclude_patterns}']
  notes: 'Auto-scoped from shape detection (shape: {shape}, confidence: {confidence}).{corpus_caveat}'
```

Name the skill with the helper that names every brief, by `{unitDetectionHeuristicsPath}`'s Unit Names, so the name the brief gets is the name the coexistence check looks up:

```bash
uv run {skillInventoryHelper} derive-name --from - --skills-folder "{skills_output_folder}" <<'SKF_SKILL_NAME'
[{"target": "{project_path}", "manifest_name": <name>, "private": <private>, "members": [<member names>]}]
SKF_SKILL_NAME
```

`manifest_name` is the umbrella candidate's `name` when §3b merged on the umbrella facade trigger, else the §2 scan-root manifest's `name` (null without one), and `private` that manifest's `private`. `members` lists the `name` of every §2 member manifest whose `private` is not `true` (`[]` for a single package): a merged monorepo whose root names no published package takes the name they share (`aws-sdk` for the `@aws-sdk/*` packages), else the repository's. `{skill_name}` ← `names[0].name`; when it is null (a target with no folder name), name the skill after the analyzed folder yourself.

When `names[0].existing` is not null and names a skill §0c did not present (a skill from another source that already has the name this brief gets), present the §0c step 4 prompt with it as the one `matches[]` entry before §7 writes anything: [M]erge and [S]kip run as in §0c step 5 and stop there; [A]longside, the headless choice, sets `{coexistence_suffix}` to `-wiki` and continues here. Then, if `{coexistence_suffix}` is non-empty, append it to the skill name.

For the brief's `language` field, **reuse `{detected_language}` from §5** — do not re-detect (the §5 helper already resolved js-vs-ts from `tsconfig.json` and Java-vs-Kotlin from the tree).

### 6b. Seed Companion Corpora (whole-language references only)

Runs only when §3 classified the repo as `language-reference` **via a whole-language signal** — the `signals` array contains a `grammar_file:` or `tree_triad:` entry (a compiler / interpreter / grammar repo such as rust-lang/rust, TypeScript, CPython). **Skip** when `language-reference` fired only from `parser_producer:` / `parser_dep:` signals (a parser *library* such as pest or lalrpop): there the code **is** the product, so no companion prose is needed and the §6/§7 caveat below does not apply.

A whole-language skill's value is in the language's **prose** — the guide/Book, the standard/library API docs, idioms — not the compiler internals. Seed those canonical corpora so the forged skill teaches the language rather than its implementation.

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}` and **`{languageCorporaHelper}`** from `{languageCorporaProbeOrder}` (first existing path wins).

1. **Derive the corpus language key `{corpus_language}`.** Prefer `{detected_language}` (from §5) when non-empty. Otherwise — a manifest-less toolchain such as CPython or Ruby — resolve it from the file paths harvested in §2:
   ```bash
   echo '{"tree": [<harvested §2 file paths>]}' | uv run {detectLanguageHelper}
   ```
   Use its `language` field. (`.c`/`.h`/`.y` are not in the detector's extension map, so a C-hosted language resolves by its real sources — Ruby via `.rb`.)
2. **Look up canonical corpora:**
   ```bash
   uv run {languageCorporaHelper} --language {corpus_language}
   ```
   - exit 0 → parse the `[{url, label, source}]` array (each seed carries `source: language-registry`) → these are `{corpus_seeds}`.
   - exit 1 → no registry entry (long-tail language) → `{corpus_seeds}` is empty (README detection in brief-skill remains the only source).
   - exit 2 → log a warning and treat as empty (best-effort; never halt).
3. Record `{N}` = number of seeds and `{corpus_labels}` = comma-joined labels, carried into the brief `doc_urls` (§8) and the honest caveat (§6/§7).
4. Build `{corpus_caveat}` (appended to `scope.notes` in §6/§8 and surfaced in §7) so the operator knows a code-only whole-language skill is low-value:
   - `{N}` ≥ 1: `" LANGUAGE-REFERENCE CAVEAT: this skill's value is the {corpus_language} prose (guide/Book + std/library docs), not compiler internals. Seeded {N} corpus URL(s): {corpus_labels}. create-skill foregrounds this registry prose as the skill's Language Guide and demotes compiler-internal signatures to a reference-only section — review the forged skill if compiler internals still dominate."`
   - `{N}` == 0: `" LANGUAGE-REFERENCE CAVEAT: no canonical corpora were found for {corpus_language} (README detection and the registry both came up empty). This skill is LOW-VALUE as code-only — attach the {corpus_language} guide + std/library docs manually (re-run with a doc URL, or enrich via US) before forging."`

   For a parser-library `language-reference` (skipped above) and every other shape, `{corpus_caveat}` is empty.

### 4a. Multi-Scope Decomposition

This section is reached only from §3b when the cohesion check decided to **split** a monorepo (members are independently published with distinct surfaces and no umbrella re-exports them). It replaces §4→§5→§6 for repos that will produce N > 1 skills.

**Decompose by workspace package:** Use workspace package discovery from §2 manifest scan results. Each workspace package with its own manifest becomes a separate skill boundary; trivial workspace members (no source files, no exports) are excluded. Name the boundaries in one call to the helper that names every brief, one entry per boundary with its manifest `name` and `private` from §2:

```bash
uv run {skillInventoryHelper} derive-name --from - --skills-folder "{skills_output_folder}" <<'SKF_BOUNDARY_NAMES'
[{"target": "<boundary path>", "manifest_name": "<its manifest name>", "private": <its private flag>}, ...]
SKF_BOUNDARY_NAMES
```

Each boundary's skill name is its `names[].name`: boundaries whose names would clash are already told apart by their parent folders, and the entries `unnamed` and `duplicates` list take a name you give them from their folder. A name whose `existing` is not null belongs to a skill from another source (§0c already offered the ones from this repository): give that boundary the `-wiki` suffix, as [A]longside does, and log `"coexistence: {name} exists, forging {name}-wiki alongside"`. Then append `{coexistence_suffix}` to every name that does not already end with it, when it is non-empty.

**Per-boundary shape→scope mapping:**

For each decomposed boundary, apply the shape→scope mapping from §4 independently — re-run the shape→scope heuristic ladder from `step-shape-detect.md` per package using each package's own manifest data. Packages may have different shapes (e.g., a `library-API` core + a `reference-app` CLI).

### 5a. Generate Multi-Scope Patterns

For each decomposed boundary, generate include/exclude patterns using the same language-aware rules as §5, but scoped to the boundary's source paths. Monorepo boundaries are rooted at the package path (e.g., `packages/auth/src/**/*.ts` instead of `src/**/*.ts`).

### 6a. Build Multi-Scope

For each boundary, build a scope object following the same structure as §6.

Include decomposition metadata in `scope.notes`: "Decomposed from {project_name} — boundary {i}/{N} ({reason})"

Each boundary's skill name is the one §4a gave it, suffix included. Detect the primary language from each boundary's manifest ecosystem (same rules as §6).

**Pin data (from §0b):** All N decomposed briefs share the same pin — the pin targets a repo-level ref, not a package-level version. Apply the same `target_version`/`target_ref` values from §0b to all N boundaries at brief write time (§8).

After building all N scopes, continue to §7 with the full set of boundaries.

### 7. Write Analysis Report

Update {outputFile} with auto-scope results. If the write fails, HARD HALT with exit code 4 (`write-failed`) per `references/headless-contract.md`.

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
  reason: 'package_threshold'
  boundary_count: N
```

Each `confirmed_units` entry includes `boundary_path` — the relative path to the boundary's root (e.g., `packages/core`). Omit the `decomposition` key entirely when single-scope (N = 1).

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

**When the shape is a whole-language `language-reference`** (§6b ran — a `grammar_file:`/`tree_triad:` signal), append a Companion Corpora subsection so the operator sees whether the skill has the prose that makes it useful. The status is computed from the **final** brief `doc_urls` (the entries that will actually be fetched), not the seed count alone:

```markdown
## Companion Corpora (language-reference)

**Why:** A whole-language skill's value is its prose (guide/Book, std/library docs, idioms), not compiler internals.
**Corpora in brief doc_urls:** {final_doc_urls_count}
  - {label}: {url}   # one line per doc_urls entry
**Status:** {ATTACHED — canonical corpora present | DEGRADED — code-only, no canonical corpora; attach the {corpus_language} guide + std/library docs before forging}
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

Create directory `{forge_data_folder}/{skill_name}/` if it does not exist. If a brief write fails, HARD HALT with exit code 4 (`write-failed`) per `references/headless-contract.md`.

Write `{forge_data_folder}/{skill_name}/skill-brief.yaml` conforming to the skill-brief schema (`{briefSchemaPath}`):

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
  notes: 'Auto-scoped from shape detection (shape: {shape}, confidence: {confidence}).{corpus_caveat}'
description: '{1-3 sentence description based on shape, language, and manifest name}'
forge_tier: '{forge_tier}'
created: '{current_date}'
created_by: '{user_name}'
```

**Companion corpora (whole-language references).** When §6b produced `{corpus_seeds}` (`{N}` ≥ 1), add them as the brief's `doc_urls` so the language's prose is fetched and assembled alongside the code:

```yaml
doc_urls:
  - { url: '{seed.url}', label: '{seed.label}', source: '{seed.source}' }   # one entry per §6b seed; source is 'language-registry'
```

These are the brief's *existing* `doc_urls`; brief-skill's README detection then merges additional discovered docs on top (existing entries win). **When `{N}` is 0, omit the `doc_urls` key entirely** — the schema requires at least one entry when the key is present.

**When decomposition is active (N > 1 units):**

Loop over all N boundaries. For each boundary:
- `name` is the boundary's §4a skill name (e.g., `trpc-server` for `@trpc/server`)
- `include`/`exclude` patterns are boundary-scoped (from §5a)
- `scope.notes` includes decomposition context: "Decomposed from {project_name} ({N} skills) — boundary {i}/{N}: {boundary_description}"
- `description` references the parent project and boundary role (e.g., "Core library package of the my-monorepo project, providing...")
- All N briefs share the same `version`, `source_repo`, `language`, `forge_tier`, `created`, `created_by` values as the parent project

**Version detection:** Attempt to auto-detect the source version per the version detection rules in `{briefSchemaPath}`. Fall back to `1.0.0` if detection fails.

**Pin data (from §0b):** When `{pinned_ref}` is non-null, enrich the brief with pin data:

- If `{pinned_ref_type}` is `"tag"`: set `target_version` = `{pinned_version}`, `target_ref` = `{pinned_ref}`, `version` = `{pinned_version}`.
- If `{pinned_ref_type}` is `"branch"`: set `target_ref` = `{pinned_ref}`, leave `target_version` = null, `version` = auto-detected or `1.0.0`.
- If `{pinned_ref_type}` is `"local"`: set `target_version` = `{pinned_version}`, `target_ref` = null, `version` = `{pinned_version}`.

When `{pinned_ref}` is null (no pin, no releases): leave `target_version` = null, `target_ref` = null — existing version detection applies unchanged.

In the docs-only path (`references/auto-docs-only.md`), `--pin` is ignored (already skipped at §0b). No changes to that path.

### 9. Emit Result Envelope

Emit the `SKF_ANALYZE_RESULT_JSON` envelope on stdout:

```
SKF_ANALYZE_RESULT_JSON: {"status":"success","report_path":"{outputFile_path}","brief_paths":["{brief_path_1}","{brief_path_2}",...,"{brief_path_N}"],"unit_counts":{"confirmed":N,"skipped":0,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto"}
```

`brief_paths` contains N paths (one per confirmed unit). `unit_counts.confirmed` is N.

If `{coexistence_suffix}` is non-empty (i.e., [A]longside was selected in §0c), include `"coexistence":"alongside"` in the envelope.

When `{pinned_ref}` is non-null, include `"pinned_ref":"{pinned_ref}"` and `"pinned_version":"{pinned_version}"` in the envelope. These flow downstream to BS/CS for provenance recording. When `{pinned_ref}` is null, omit these fields.

### 10. Write Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_data_folder}/analyze-source-result-latest.json`. `outputs` lists all N brief paths and `summary` includes the brief count N. If the per-run record cannot be written, HARD HALT with exit code 4 (`write-failed`) per `references/headless-contract.md`.

If `{onCompleteCommand}` is non-empty, invoke it now with `--result-path={result_json_path}`.

### 11. Chain to Health Check

Load, read fully, then execute {nextStepFile} to run the shared workflow health check.

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
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
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
- Every brief goes through the brief writer and the schema gate (§8): a brief either one rejects halts the run before any brief is written

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "auto"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 0. URL Type Detection

Read the target URL or path from the pipeline context (`{project_path}` or the first entry in `project_paths[]`).

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If neither resolves, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:0`): "`skf-skill-inventory.py` is missing. Re-install SKF." The helper that names every brief classifies the target:

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

**Resolve `{validatePinsHelper}`** from `{validatePinsProbeOrder}`; first existing path wins. If neither resolves, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:0b`): "`skf-validate-pins.py` is missing. Re-install SKF."

```bash
uv run {validatePinsHelper} --repo-url {project_path} --pin {pin_value}
```

Handle exit codes:

- **Exit 0** (`status: "valid"`): Store `{pinned_ref}` = `resolved_ref`, `{pinned_ref_type}` = `ref_type`, `{pinned_version}` = `version`. Continue to §0c.
- **Exit 1** (`status: "invalid"`): HARD HALT (exit code 3, `halt_reason: "pin-invalid"`, phase `step-auto-scope:0b`): "Version pin '{pin_value}' not found in {project_path}. Available matches: {suggestions}. Use a valid tag, branch, or omit --pin for latest."
- **Exit 2** (error): HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:0b`): "The version pin could not be checked: {the helper's error}."

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

- **[M]erge:** Offered only for entries whose `matches[].skf_skill` is true. If more than one such entry exists, prompt the user to select which one to merge into before proceeding. Read `{matched_skill_name}` = the selected entry's `matches[].name` and `{matched_active_path}` = its `matches[].active_path`. End the run as §9 says, with a redirect that signals the forger to route to the US workflow for the selected skill: write `{run_dir}/result-context.json` as

  ```json
  {"status": "redirect", "redirect_to": "US", "skill_name": "{matched_skill_name}", "skill_path": "{matched_active_path}", "mode": "auto", "coexistence": "merge", "result_contract": {"skill": "skf-analyze-source", "status": "redirect", "outputs": [], "summary": {"mode": "auto", "redirect_to": "US", "skill_name": "{matched_skill_name}"}}}
  ```

  and go to §9. **STOP HERE: do not proceed to the docs-only sub-flow or §1.**

- **[S]kip:** End the run as §9 says, with a skip: write `{run_dir}/result-context.json` as

  ```json
  {"status": "skipped", "unit_counts": {"confirmed": 0, "skipped": 1, "maybe": 0}, "mode": "auto", "coexistence": "skip", "skipped_reason": "Existing skill for {matched_skill_name}", "result_contract": {"skill": "skf-analyze-source", "status": "skipped", "outputs": [], "summary": {"mode": "auto", "skipped_reason": "Existing skill for {matched_skill_name}"}}}
  ```

  and go to §9. **STOP HERE: do not proceed to the docs-only sub-flow or §1.**

### 1. Load Context

Read {outputFile} frontmatter to obtain:
- `project_paths[]` — the root(s) to analyze
- `forge_tier` — for brief generation
- `project_name`, `user_name`, `date`

Load `references/step-shape-detect.md` as reference for shape detection invocation contract and shape→scope mapping.

### 2. Manifest Scan

Enumerate package manifests **deterministically** via `{scanManifestsHelper}` (the same helper the interactive `scan-project.md` uses): do not hand-scan. Resolve `{scanManifestsHelper}` as the first path in `{scanManifestsProbeOrder}` that exists; if none does, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:2`): "`skf-scan-manifests.py` is missing. Re-install SKF." The scanner reads a **local directory**, so how you point it at the target depends on the input form classified in §0:

**For each path in `project_paths[]`:**

- **Local filesystem path** (starts with `/`, `./`, `~/`, `~`, or is an existing directory): scan it directly. Its **scan root** is the path itself, with a leading `~` written as `$HOME`: the commands below quote every path, and a `~` inside double quotes does not expand.

  ```bash
  uv run {scanManifestsHelper} scan "<the path's scan root>"
  ```

- **Remote git URL** (e.g. `github.com/{owner}/{repo}`): auto-scope has no working tree yet and the scanner cannot read a URL. Fetch **just the manifests** into the run folder (blobless + sparse + depth-1: no source blobs, typically KB to MB even for large monorepos); `{run_dir}/clone-{i}`, for the `{i}`-th entry of `project_paths[]` (`clone-1` for §0's target), is the path's **scan root**:

  ```bash
  git clone --filter=blob:none --no-checkout --depth 1 {pinned_branch_flag} {path} "{run_dir}/clone-{i}"
  git -C "{run_dir}/clone-{i}" sparse-checkout set --no-cone '**/package.json' '**/Cargo.toml' '**/pyproject.toml' '**/go.mod' '**/pom.xml' '**/build.gradle' '**/build.gradle.kts' '**/Package.swift' 'pnpm-workspace.yaml' '**/pnpm-workspace.yaml' 'lerna.json' 'rush.json' 'nx.json'
  git -C "{run_dir}/clone-{i}" checkout
  uv run {scanManifestsHelper} scan "{run_dir}/clone-{i}"
  ```

  where `{pinned_branch_flag}` is `--branch {pinned_ref}` when a pin was resolved in §0b (so manifests match the target version), otherwise omitted. If a `git` command fails, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:2`, path `{path}`): "{path} could not be fetched: {the first stderr line}." The clone stays in the run folder until the run ends, so §3 and §5 read it in later commands.

Parse the JSON envelope: `{manifests: [{path, ecosystem, ...}], total_unique, monorepo, warnings?}`. The scanner discovers the project root plus monorepo workspace members (npm/pnpm/yarn `workspaces`, Cargo `[workspace]`, and other ecosystems) and sets the `monorepo` flag — so members are found without hand-listing each workspace convention, for both local trees and remote fetches.

From the envelope, record:

1. **Supported manifest paths**: filter `manifests[].path` to the types `skf-shape-detect.py` accepts (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Package.swift`). Each `manifests[].path` is **relative to the scan root**, so resolve them against it before use. This filtered, comma-joined list of resolved paths is fed to shape detection in §3. For a monorepo, it includes each workspace member's manifest, so the package surface is classified accurately rather than from a bare (and often export-less) repo root. The scanner may discover ecosystems shape detection does not yet classify; those are excluded here.
2. **`monorepo` flag** and the count of discovered supported packages — carried forward as a signal for the decomposition decision in §3a.
3. **The names and flags §3b, §4a and §6 read:** the scan-root manifest's `name` and `private` (the `manifests[]` entry whose `path` has no folder), each member manifest's `name`, `private` and `internal_deps`, and `umbrella_candidates[]`. Read them from the envelope; never open a member manifest for them.

**List the target's files once.** Shape detection (§3) and language detection (§5, §6a) read the whole file list of the target (`{project_path}`, §0's target) from one run file, `{run_dir}/tree.txt`, so the listing never passes through you or a shell variable. Write it with the first command that fits the target, where `{scan_root}` is the target's scan root:

```bash
git -C "{scan_root}" -c core.quotePath=false ls-tree -r --name-only HEAD > "{run_dir}/tree.txt"
git -C "{scan_root}" -c core.quotePath=false ls-files > "{run_dir}/tree.txt"
(cd "{scan_root}" && find . -type f -not -path '*/.git/*' | sed 's#^\./##') > "{run_dir}/tree.txt"
```

The first lists a remote fetch (tree objects only: the blobless clone downloads no file for it), the second a local path inside a git work tree (`git -C "{scan_root}" rev-parse --is-inside-work-tree` prints `true`), the third any other local folder. If the command fails or writes an empty file, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:2`, path `{project_path}`): "The files of {project_path} could not be listed: {the first stderr line}."

**IF no supported manifests are found** (the filtered list is empty), the repo may still be a manifest-less language toolchain (CPython, Ruby), which shape detection recognizes from the file list: proceed to §3 with an **empty** `--manifests`. Shape detection answers exit 1 (unknown) for a repo with neither, and §3 then switches to interactive mode.

### 3. Invoke Shape Detection

**Resolve `{shapeDetectHelper}`** from `{shapeDetectProbeOrder}`; first existing path wins. If neither resolves, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:3`): "`skf-shape-detect.py` is missing. Re-install SKF."

Invoke the shape detection script with the discovered manifests and the §2 file list, from which it finds the tree-level signals (grammar files, a compiler folder and its lexer, parser and ast) itself:

```bash
uv run {shapeDetectHelper} --repo-url "{project_path}" --manifests "<comma_separated_manifest_paths>" --tree-file "{run_dir}/tree.txt"
```

`<comma_separated_manifest_paths>` may be empty for a manifest-less language repo. Parse the JSON output: `{shape, signals, confidence, export_count, package_count}`

**Handle exit codes:**

- **Exit 0 (shape classified):** Continue to §3a.
- **Exit 1 (unknown shape):** the run goes on as an interactive analysis. Set `mode: 'interactive'` in {outputFile}'s frontmatter (a session that resumes this report must take the interactive chain, not re-enter auto-scope) and `{auto_mode}` to false, emit the fallback message: "**Auto-scope could not classify this repo: switching to interactive mode.**", then load, read fully, and execute `references/scan-project.md`. **STOP HERE.**
- **Exit 2 (error):** HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:3`): "Shape detection failed: {the `error` its stderr JSON names}."

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

**Record the decision** the moment you make it, so the run's result and a later halt both carry it: write `{run_dir}/decision.json` as `{"gate": "auto-scope.cohesion", "default_action": "merge", "taken_action": "<merge or split>", "reason": "<the cohesion trigger that held, or why the members split>", "evidence": {"package_count": <package_count>, "members": [<the §2 member names>]}}` and run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost.

**Facet-coverage guard (merged facet-diverse repos only).** When you merge a repo whose members have genuinely distinct surfaces and you scope to only some of them, record the decision explicitly — never drop a facet silently:

- In `scope.notes`, name the in-scope facets **and** the excluded major facets, e.g. _"Scoped to react + react-dom core; excludes react-server-dom-\* (RSC), the specialized renderers (react-art/native/test), and the compiler — forge a separate skill for those."_
- Surface the excluded facets in the analysis report (§7) so the operator can re-scope or forge a companion skill.

### 4. Map Shape to Scope

Apply the canonical **Shape → Scope Type Mapping** table from `step-shape-detect.md` (loaded at §1) — the single source of truth for this ladder (the `export_count > 200 → public-api` split, the `language-reference` corpora caveat, and the `stack-compose` decomposition note).

### 5. Generate Include/Exclude Patterns

Generate `scope.include` and `scope.exclude` arrays from the detected language and project structure.

**Detect the primary language once, deterministically**, from the §2 file list, via the shared helper: the single source of truth for the manifest→language rule table. **Resolve `{detectWorkspacesHelper}`** from `{detectWorkspacesProbeOrder}` and **`{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:5`): "`{the missing script}` is missing. Re-install SKF." First find the workspace layout, which reads the root manifests from the scan root (§2):

```bash
uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree.txt" --manifest-dir "{scan_root}"
```

`{workspace_kind}` ← its `manifest_kind` (null when it exits non-zero). Then detect the language, passing `--workspace-signal {workspace_kind}` only when `{workspace_kind}` is not null, so a Cargo or Python workspace root wins over a nested package.json:

```bash
uv run {detectLanguageHelper} --tree-file "{run_dir}/tree.txt" [--workspace-signal {workspace_kind}]
```

The helper owns the `tsconfig.json` JS-vs-TS and `build.gradle` Java-vs-Kotlin disambiguation, ranks the manifests nearest the root first, and never lets a manifest in a docs, example, test or tool folder decide while another one exists. Read `{detected_language}`:

- **`detected_languages` has one entry or none, or `.confidence` is `high` and the §2 scan-root manifests (the `manifests[]` entries whose `path` has no folder) are all of one ecosystem:** `{detected_language}` ← `.language`. A manifest at the root decided, so the choice below would give the same answer.
- **Otherwise** (several languages, and no single-ecosystem root manifest decided): `.language` is the helper's first guess, not the answer. Choose the language the skill documents: among `detected_languages`, the language of the scan-root manifest (the §2 `manifests[]` entry whose `path` has no folder; with several, the one whose `name` is the package this repository publishes), or, when there is none, `.source_language`, the language most of the files are written in (CPython's listing holds only manifests below its root, so `.confidence` is `medium` and its sources say `python`). Record the choice: write `{run_dir}/decision.json` as `{"gate": "auto-scope.language", "default_action": "<detected_languages[0]>", "taken_action": "<the language you chose>", "reason": "<the manifest or the source files that decided>", "evidence": {"detected_languages": [<detected_languages>], "source_language": "<source_language>"}}` and run `uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (if it fails, go on).

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

The single-scope brief's scope (§8 hands these values to the brief writer):

- `scope.type`: the §4 mapped scope type
- `scope.include` and `scope.exclude`: the §5 patterns
- `scope.notes`: `Auto-scoped from shape detection (shape: {shape}, confidence: {confidence}).{corpus_caveat}`, with §6b's `{corpus_caveat}` (empty unless §6b ran)

Name the skill with the helper that names every brief, by `{unitDetectionHeuristicsPath}`'s Unit Names, so the name the brief gets is the name the coexistence check looks up:

```bash
uv run {skillInventoryHelper} derive-name --from - --skills-folder "{skills_output_folder}" <<'SKF_SKILL_NAME'
[{"target": "{project_path}", "manifest_name": <name>, "private": <private>, "members": [<member names>]}]
SKF_SKILL_NAME
```

`manifest_name` is the umbrella candidate's `name` when §3b merged on the umbrella facade trigger, else the §2 scan-root manifest's `name` (null without one), and `private` that manifest's `private`. `members` lists the `name` of every §2 member manifest whose `private` is not `true` (`[]` for a single package): a merged monorepo whose root names no published package takes the name they share (`aws-sdk` for the `@aws-sdk/*` packages), else the repository's. `{skill_name}` ← `names[0].name`; when it is null (a target with no folder name), name the skill after the analyzed folder yourself.

When `names[0].existing` is not null and names a skill §0c did not present (a skill from another source that already has the name this brief gets), present the §0c step 4 prompt with it as the one `matches[]` entry before §7 writes anything: [M]erge and [S]kip run as in §0c step 5 and stop there; [A]longside, the headless choice, sets `{coexistence_suffix}` to `-wiki` and continues here. Then, if `{coexistence_suffix}` is non-empty, append it to the skill name.

### 6b. Seed Companion Corpora (whole-language references only)

Runs only when §3 classified the repo as `language-reference` **via a whole-language signal** — the `signals` array contains a `grammar_file:` or `tree_triad:` entry (a compiler / interpreter / grammar repo such as rust-lang/rust, TypeScript, CPython). **Skip** when `language-reference` fired only from `parser_producer:` / `parser_dep:` signals (a parser *library* such as pest or lalrpop): there the code **is** the product, so no companion prose is needed and the §6/§7 caveat below does not apply.

A whole-language skill's value is in the language's **prose** — the guide/Book, the standard/library API docs, idioms — not the compiler internals. Seed those canonical corpora so the forged skill teaches the language rather than its implementation.

**Resolve `{languageCorporaHelper}`** from `{languageCorporaProbeOrder}` (first existing path wins). The lookup is best-effort: when neither path exists, record the warning `language_corpora_unavailable: skf-language-corpora.py is missing` with `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'` and treat `{corpus_seeds}` as empty.

1. **The corpus language key `{corpus_language}`** ← `{detected_language}` from §5, which a manifest-less toolchain such as CPython or Ruby gets from its source files.
2. **Look up canonical corpora:**
   ```bash
   uv run {languageCorporaHelper} --language {corpus_language}
   ```
   - exit 0 → parse the `[{url, label, source}]` array (each seed carries `source: language-registry`) → these are `{corpus_seeds}`.
   - exit 1 → no registry entry (long-tail language) → `{corpus_seeds}` is empty (README detection in brief-skill remains the only source).
   - exit 2 → record the warning `language_corpora_failed: <its first stderr line>` the same way and treat as empty (best-effort; never halt).
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

This is the one statement of what each boundary's brief holds; §8 writes these values and the ones every brief shares (version, `source_repo`, `forge_tier`, `created`, `created_by` and the §0b pin: the pin targets a repo-level ref, not a package-level version). For boundary `{i}` of `{N}`:

- **Name:** the one §4a gave it, suffix included.
- **Scope:** `scope.type` from its §4a mapping, `scope.include` and `scope.exclude` from §5a, and `scope.notes` ← `Decomposed from {project_name} ({N} skills): boundary {i}/{N}, {boundary role}.`, where `{boundary role}` says in a few words what the boundary is for (for example `core library` or `CLI`).
- **Language:** detected from the boundary's own files, without `--workspace-signal` (the workspace root's language would answer for every boundary):

  ```bash
  awk -v p="<boundary path>/" 'index($0, p) == 1' "{run_dir}/tree.txt" > "{run_dir}/tree-{i}.txt"
  uv run {detectLanguageHelper} --tree-file "{run_dir}/tree-{i}.txt"
  ```

  Read it as §5 says, the boundary's own manifest standing for the scan-root manifest.
- **Description:** one to three sentences naming the parent project and the boundary's role (for example "Core library package of the my-monorepo project, providing...").

After building all N scopes, continue to §7 with the full set of boundaries.

### 7. Write Analysis Report

Update {outputFile} with auto-scope results. If the write fails, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `step-auto-scope:7`, path `{outputFile}`): "The analysis report could not be written: {the error}."

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

### 8. Write Skill Briefs

The brief writer renders, checks and writes every brief, and applies the version precedence (`target_version`, then `detected_version`, then `1.0.0`) and the rule that `target_version` equals `version`. This section supplies values and never writes YAML. **Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}` and **`{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins for each. If one has no candidate, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:8`): "`{the missing script}` is missing. Re-install SKF."

**For each confirmed unit** (1 for single-scope, N for decomposition), write its context as `{run_dir}/brief-{skill_name}.json`, a file and never an echo'd string (the language caveat holds an apostrophe):

```json
{
  "name": "{skill_name}",
  "target_version": "{target_version from the pin table, or null}",
  "target_ref": "{target_ref from the pin table, or null}",
  "detected_version": "{detected_version, or null}",
  "source_type": "source",
  "source_repo": "{project_path}",
  "language": "{detected_language}",
  "description": "{1-3 sentence description based on shape, language, and manifest name}",
  "forge_tier": "{forge_tier}",
  "created": "{current_date}",
  "created_by": "{user_name}",
  "scope_type": "{scope_type}",
  "scope_include": ["{include_patterns}"],
  "scope_exclude": ["{exclude_patterns}"],
  "scope_notes": "{scope.notes}",
  "scope_rationale": null,
  "scope_tier_a_include": null,
  "scope_amendments": null,
  "scope_registry_path": null,
  "scope_ui_variants": null,
  "scope_demo_patterns": null,
  "doc_urls": null,
  "scripts_intent": null,
  "assets_intent": null,
  "source_authority": null,
  "source_ref": null
}
```

Only `description` and `scope_notes` are in your words. Every other value comes from an earlier section:

- `name`, `scope_type`, `scope_include`, `scope_exclude` and `scope_notes`: §6 for a single scope; §6a for each boundary of a decomposition.
- `language`: §5's `{detected_language}` for a single scope (detect once); §6a's for each boundary.
- `detected_version`: the version the §2 scan-root manifest declares, found by the Version Detection rules in `{briefSchemaPath}`, when it is full `X.Y.Z` semver (an optional leading `v`, an optional pre-release such as `-rc.1`); else null (a two-part or PEP 440 version such as `0.1` or `2.0.0rc1` too), since the writer rejects any other value. The writer falls back to `1.0.0` for null.
- `target_version` and `target_ref`, from the §0b pin, the same for every brief:

  | `{pinned_ref_type}` | `target_version` | `target_ref` |
  |---|---|---|
  | `"tag"` | `{pinned_version}` | `{pinned_ref}` |
  | `"branch"` | null | `{pinned_ref}` |
  | `"local"` | `{pinned_version}` when it is a version (`X.Y.Z`, with an optional leading `v`), else null | null |
  | null (no pin, no release) | null | null |

- `doc_urls`: when §6b produced `{corpus_seeds}` (`{N}` ≥ 1), one `{"url": "{seed.url}", "label": "{seed.label}", "source": "{seed.source}"}` per seed (its `source` is `language-registry`), so the language's prose is fetched and assembled alongside the code; brief-skill's README detection then merges more docs on top (existing entries win). Otherwise null.

**Gate every brief before any is written.** For each one, render it into the run folder and run on it the schema check skf-brief-skill runs when it reads a brief:

```bash
uv run {writeSkillBriefHelper} write --target "{run_dir}/briefs/{skill_name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{skill_name}.json"
uv run {validateBriefSchemaHelper} "{run_dir}/briefs/{skill_name}/skill-brief.yaml"
```

When the writer exits non-zero or the validator answers `valid: false`, the brief is rejected: HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `step-auto-scope:8`, path `{forge_data_folder}/{skill_name}/skill-brief.yaml`): "The brief for {skill_name} was rejected: {the writer's `message` and `field`, or each `errors[].message` of the validator}." No brief reaches `{forge_data_folder}` then, so the run never reports a brief that does not validate.

**Then write each brief** to its place, from the same context (the writer renders the same bytes, creates the folder and writes atomically):

```bash
uv run {writeSkillBriefHelper} write --target "{forge_data_folder}/{skill_name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{skill_name}.json"
```

Keep each `brief_path` it prints for §9. If it exits non-zero, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `step-auto-scope:8`, path `{forge_data_folder}/{skill_name}/skill-brief.yaml`, with `unit_counts` and the `brief_paths` written so far): "The brief for {skill_name} could not be written: {its `message`}."

### 9. End the Run

The shared emitter writes the result files and prints the envelope; this section stages their content, in every mode. After §8, write `{run_dir}/result-context.json` (a redirect or a skip from §0c has already written its own and comes here directly):

```json
{
  "status": "success",
  "report_path": "{outputFile as an absolute path}",
  "brief_paths": ["{the brief_path of each brief §8 wrote}"],
  "unit_counts": {"confirmed": <N>, "skipped": 0, "maybe": 0},
  "mode": "auto",
  "result_contract": {
    "skill": "skf-analyze-source",
    "status": "success",
    "outputs": [{"type": "report", "path": "{outputFile as an absolute path}"}, {"type": "brief", "path": "{each brief_path}"}],
    "summary": {"mode": "auto", "shape": "{shape}", "brief_count": <N>, "units": ["{each skill_name}"]}
  }
}
```

Add `"coexistence": "alongside"` when `{coexistence_suffix}` is non-empty ([A]longside was selected in §0c), `"pinned_ref": "{pinned_ref}"` when `{pinned_ref}` is non-null, and `"pinned_version": "{pinned_version}"` when `{pinned_version}` is non-null (a branch pin, or a latest release whose tag is not a version, has none): these flow downstream to BS/CS for provenance recording. Put the same pin fields in `summary`. Then run:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-analyze-source --run-dir "{run_dir}" --result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"
```

The emitter stamps the UTC time, the run id and the decisions and warnings the run recorded into the record, writes `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` and its `analyze-source-result-latest.json` copy, and prints the `SKF_ANALYZE_RESULT_JSON:` line on stdout (field rules in `references/headless-contract.md`). When `{headless_mode}` is true, display the line verbatim. A result file that could not be written leaves the line's `result_path` null and a `result_file_write_failed` warning in it, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `step-auto-scope:9`, path `{forge_data_folder}`): "The result contract could not be written: {its message}."

If `{onCompleteCommand}` is non-empty and the line's `result_path` is not null, invoke it now: `{onCompleteCommand} --result-path={forge_data_folder}/analyze-source-result-latest.json`. Display a hook failure; it never fails the run.

Then delete the run folder, whose payloads the emitter has read: `rm -rf "{run_dir}"`. Load, read fully, then execute {nextStepFile} to run the shared workflow health check.

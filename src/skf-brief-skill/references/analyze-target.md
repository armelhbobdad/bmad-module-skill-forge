---
nextStepFile: 'scope-definition.md'
versionResolutionFile: 'references/version-resolution.md'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
emitBriefEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-brief-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Analyze Target

## STEP GOAL:

To analyze the target repository by resolving its location, reading its structure, detecting the primary language, and listing top-level modules and exports — providing the user with a factual foundation for scoping decisions.

## Rules

- Focus only on analysis — do not define scope yet (Step 03)
- Do not make scoping decisions or recommendations
- Do not hallucinate or guess about repository contents
- All user-facing output in `{communication_language}`

## MANDATORY SEQUENCE

### 1. Resolve Target Location

**For GitHub URLs:**

**Resolve the analysis ref first.** `{analysis_ref}` is the git ref every GitHub-API fetch in this step (tree, manifests, contents) reads from — resolve it before fetching anything so the analyzed structure matches the version being skilled:
- If neither `target_ref` nor `target_version` was set in step 01: `{analysis_ref}` = `HEAD` (default branch). This is the common case — skip straight to the probes below with no extra call.
- If `target_ref` is set (an explicit ref the user stated verbatim, highest priority): use it directly as `{analysis_ref}` — no tag lookup.
- If `target_version` is set: resolve it to a tag via `gh api repos/{owner}/{repo}/git/refs/tags` (paginate if the repo has many tags), matching in priority order — exact `{target_version}`, then `v{target_version}`. This mirrors the clone-path tag matching in `skf-create-skill/references/source-resolution-protocols.md` (see that file for the full monorepo-tag priority if the simple forms miss). On a single match, set `{analysis_ref}` to that tag. On **multiple matches**, present them and ask which to use (headless: take the exact match, else the `v`-prefixed one). On **zero matches**, warn `"No git tag matches version {target_version}; analyzing the default branch (HEAD) instead — structure and exports may not match the pinned version."`, set `{analysis_ref}` = `HEAD`, and record the fallback in the §5 analysis summary.

- Issue both probes in **one message with two parallel Bash calls** — they are independent:
  - `gh api repos/{owner}/{repo}` (verify repo exists)
  - `gh api repos/{owner}/{repo}/git/trees/{analysis_ref}?recursive=1` (fetch file tree at the resolved ref)
- If the repo-existence probe fails, fall through to the failure-class triage below; the tree response from the parallel call is discarded in that case.

**Truncation detection:** After receiving the tree response, check the `truncated` field in the JSON output. If `truncated: true`:
- Display: "Note: GitHub API returned a truncated tree response ({count} items). Full analysis may require a local clone."
- Record in analysis summary: "Tree listing is partial — some files may not appear in the analysis."
- For very large repos (>1000 files in tree response): offer a recovery path instead of just warning. Interactive — present:
  ```
  Tree is truncated. How would you like to proceed?
    [L] Clone locally and re-analyze (slower but complete)
    [P] Proceed with the partial tree (faster, may miss exports under deeper paths)
  ```
  On `[L]`: shallow-clone (`git clone --depth 1 {url} {tmp_dir}`), restart this section against the local path, and remove `{tmp_dir}` after the analysis summary in §5. On `[P]` (or under headless): record `tree_truncated: true` in the analysis summary and continue without HALT.

**On API failure (non-200 from `gh api`):**

Distinguish the failure class before reporting. In headless mode, every branch below emits the error envelope per **step 5 §4b** with its stated `halt_reason` before the HALT (pass the resolved `{skill_name}`, or the `"unknown"` placeholder documented in §4b if it is not yet set):
- Auto-run `gh auth status` and capture its output. If it reports an unauthenticated state or expired token: emit the error envelope per **step 5 §4b** with `halt_reason: "gh-auth-failed"`, then HALT (exit code 3, `halt_reason: "gh-auth-failed"`) — "**Error:** GitHub CLI is not authenticated. `gh auth status` says: `{captured output}`. Run `gh auth login` and retry."
- If `gh auth status` reports authenticated but the call still failed (404/403): emit the error envelope per **step 5 §4b** with `halt_reason: "target-inaccessible"`, then HALT (exit code 3, `halt_reason: "target-inaccessible"`) — "**Error:** Cannot access repository at `{url}`. The CLI is authenticated but the API returned `{status}`. Check the URL and that the account has access to private repositories if applicable."
- If `gh auth status` itself fails to run (binary missing): emit the error envelope per **step 5 §4b** with `halt_reason: "gh-auth-failed"`, then HALT (exit code 3, `halt_reason: "gh-auth-failed"`) — "**Error:** `gh` CLI not found on PATH. Install it from <https://cli.github.com> and re-run."

**For local paths:**
- Verify the directory exists
- List the directory tree
- If path doesn't exist: **HALT** — "**Error:** Directory not found at {path}. Verify the path is correct."

Display: "**Resolving target...**"

### 1b. Detect Monorepo / Workspace Layout

**Resolve `{detectWorkspacesHelper}`** from `{detectWorkspacesProbeOrder}`; first existing path wins. HALT if no candidate exists.

Delegate workspace detection to `{detectWorkspacesHelper}` instead of reasoning through manifest rules in prose. Build a payload from the tree fetched in §1 plus the small set of root manifests the detector needs, then invoke the script:

```bash
echo '{"tree": [<flat list of repo-relative file paths>], "manifests": {"package.json": "<raw text>", "Cargo.toml": "<raw text>", "pnpm-workspace.yaml": "<raw text>", "lerna.json": "<raw text>"}}' | \
  uv run {detectWorkspacesHelper}
```

- **`tree`** — pass the flat list of repo-relative file paths already fetched in §1 (for GitHub: the `path` values from the `gh api .../git/trees/{analysis_ref}?recursive=1` response; for local: the equivalent listing).
- **`manifests`** — only the root manifests need contents; child-workspace manifests are looked up from the tree by the script. Include any of `package.json`, `Cargo.toml`, `pnpm-workspace.yaml`, `lerna.json` that appears at the repo root. Fetch them in **one message with N parallel Bash calls** (`gh api .../contents/{path}?ref={analysis_ref}` for GitHub, file reads for local), then base64-decode together. Per-workspace manifest contents (e.g. `packages/foo/package.json`) are optional — including them populates the workspace `name` field with the manifest's declared package name; omitting them falls back to the directory basename.

The script returns a JSON envelope: `{is_monorepo, manifest_kind, workspaces[], warnings[]}`. Apply the result deterministically — see `src/shared/scripts/schemas/workspace-detection.v1.json` for the full contract.

**If `is_monorepo: false`** — skip this section silently and continue to §2.

**If `is_monorepo: true`** — present the discovered workspaces and prompt:

```
This looks like a monorepo ({manifest_kind}) with these workspaces:
  1. {workspaces[0].name} ({workspaces[0].path})
  2. {workspaces[1].name} ({workspaces[1].path})
  ...
Which one should the skill cover? Pick a number, or type 'all' to scope at the repo root.
```

Interactive: wait for the user choice. On a numbered choice, store `monorepo_workspace: {path}` and rebase §2-§4b against that path. On `'all'`, leave `monorepo_workspace` unset and proceed at the repo root with a note in the analysis summary that scope is unfiltered.

Headless: if the input contract supplied an `include` glob that begins with one of the workspace paths, auto-select that workspace (log `"headless: auto-selected workspace {name} from include glob"`). Otherwise default to repo root and log `"warn: monorepo detected ({manifest_kind}) but no workspace pre-selected — analyzing at repo root"`.

Surface any non-empty `warnings[]` from the script to the operator log so a malformed root manifest is debuggable; the workflow does not HALT — falling back to repo-root analysis is always safe.

**`cross-ecosystem workspace ignored` warning:** when a root workspace manifest from a different language ecosystem co-exists with the surfaced one (e.g. a root `Cargo.toml [workspace]` alongside a pnpm workspace), the script surfaces only the higher-priority kind and emits this warning naming the ignored kind and its member count. The ignored ecosystem's workspaces are **not** in `workspaces[]`, so the numbered menu above will not list them. When this warning is present, tell the operator both ecosystems exist and ask which the skill should cover; if they pick the ignored ecosystem, scope §2-§4b at its root (or the relevant member) rather than the surfaced workspace, and carry the ignored kind into §3 (see the `workspace_signal` note there).

### 2. Read Repository Structure

List the top-level directory structure:

"**Repository Structure:**
```
{repo-name}/
├── {top-level files}
├── {top-level directories}/
│   └── ...
└── ...
```
**Total:** {file count} files, {directory count} directories"

### 3. Detect Primary Language

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins. HALT if no candidate exists.

Delegate the rule walk to `{detectLanguageHelper}` instead of evaluating manifest presence and extension frequency in prose:

```bash
echo '{"tree": [<flat list of repo-relative file paths from §1>], "workspace_signal": "<§1b manifest_kind, or omit when null>"}' | uv run {detectLanguageHelper}
```

Pass the §1b `manifest_kind` as `workspace_signal` (omit the key when it is `null` / not a monorepo). This gives the workspace root precedence: for a `cargo-workspace` or `python-multi-package` root, the script returns the root language (rust/python) instead of being misled into `typescript` by a nested `package.json` + `tsconfig.json` in a non-workspace subdirectory (e.g. a `docs/` or `website/` site). JS-family workspace kinds (`npm-workspaces`/`pnpm-workspaces`/`lerna`) carry no override — their root `package.json` resolves js/ts normally.

**When §1b surfaced a `cross-ecosystem workspace ignored` warning and the operator chose the ignored ecosystem:** pass that ignored kind as `workspace_signal` (not the surfaced kind), so a co-located `cargo-workspace`/`python-multi-package` root resolves to rust/python instead of being pinned to the surfaced ecosystem's language by the workspace that won detection priority.

The script returns `{language, confidence, detection_source, fallback_to_extension_frequency}` after walking the documented rule table (the `workspace_signal` precedence above first, then manifest presence — package.json with tsconfig.json disambiguation, Cargo.toml, pyproject.toml/setup.py/setup.cfg, go.mod, pom.xml, build.gradle.kts, build.gradle Groovy with Java/Kotlin disambiguation, *.csproj/*.sln, Gemfile — then extension-frequency fallback over recognized source extensions). Use the returned values directly:

"**Detected language:** {language}
**Confidence:** {confidence}
**Detection source:** {detection_source}"

If `confidence` is `low` (or `unknown` is returned for `language`): flag for user override in step 03 §4.

### 4. List Top-Level Modules and Exports

**Resolve `{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}`; first existing path wins. HALT if no candidate exists.

Identify the public API surface. **Delegate the parsing to `{extractPublicApiHelper}` whenever the detected language is supported** — the script is the single source of truth for manifest parsing, export discovery, and version detection across the whole SKF pipeline. Hand-rolling these in prose creates drift seams the LLM cannot fully close.

**Script-supported languages** (use the script): `js`, `ts`, `javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`.

This section runs exactly one of §4.1 (script path) or §4.2 (fallback path) based on the detected language, then always emits §4.3 (output format) and conditionally §4.4 (semantic signals).

#### 4.1 Procedure — script-supported languages

1. Read the relevant files into memory (no parsing yet — just collect content). For GitHub sources, issue **all N `gh api repos/{owner}/{repo}/contents/{file}?ref={analysis_ref}` calls in a single message with N parallel Bash calls** (one per manifest + each entry point), then base64-decode the responses together — these are 2-4 independent fetches per typical run. Carrying `{analysis_ref}` through here is what keeps the analyzed exports/version aligned with the pinned tag rather than HEAD. For local sources read directly (also parallelisable, but local reads are fast enough that serial Read tool calls are acceptable).

   | Language | Manifest | Entry points (mode=quick) |
   |----------|----------|--------------------------|
   | js / ts / javascript / typescript | `package.json` (root, or primary workspace package per `references/version-resolution.md`) | `index.{ts,js}` and/or `src/index.{ts,js}` if present |
   | python | `pyproject.toml` (or `setup.py` / `setup.cfg` if no `pyproject.toml`) | top-level `__init__.py` of the package, plus `_version.py` if present |
   | rust | `Cargo.toml` (`[package]` — workspace root if `version = { workspace = true }`) | `src/lib.rs` |
   | go | `go.mod` | top-level `*.go` exporting the package surface |
   | java | `pom.xml` | (manifest alone is sufficient for the modules listing) |
   | kotlin | `build.gradle` / `build.gradle.kts` | (manifest alone) |

2. Build a JSON payload matching the script contract:

   ```json
   {
     "language": "<one of the supported values>",
     "manifest": {"path": "<relative path>", "content": "<file contents>"},
     "entries":  [{"path": "<relative path>", "content": "<file contents>"}, ...],
     "mode":     "quick"
   }
   ```

3. Invoke the script and parse its JSON stdout:

   ```bash
   echo '<payload-json>' | uv run {extractPublicApiHelper} --mode quick
   ```

   On a non-zero exit (codes 1 or 2 per the script's docstring), capture stderr, log it, and fall through to §4.2 (the prose-fallback path) — never HALT just because the script choked on an unusual manifest.

4. Render the returned `package_name`, `exports` (each entry's `name`/`type`/`source_file`), `dependencies`, and any `warnings` to the user. The script also returns `version` — feed that into §4b instead of re-deriving.

5. The script does not enumerate directories under `src/`. The LLM still lists those as "Top-Level Modules/Directories" so the user sees structural context (Maven and Gradle are the exception — for those, the script returns a `modules` array which IS the list).

#### 4.2 Procedure — fallback (not script-supported)

Languages outside the script coverage (Ruby / C# / Swift / etc.) take this path. The §4.1 fall-through on script error also lands here.

Fall back to ad-hoc inspection — `Gemfile` / `*.csproj` / `*.sln` / `Package.swift` / file extension frequency. List top-level source directories as potential modules and note any obvious entry points. Flag the limitation in the analysis summary so the user knows scoping is on coarser signals.

#### 4.3 Output format (both paths)

"**Top-Level Modules/Directories:**
{numbered list of modules with brief description of each}

**Detected Exports/Entry Points:**
{numbered list of public-facing items found — from script output when available, ad-hoc inspection otherwise}"

#### 4.4 Semantic Signals (Forge+/Deep with ccc only)

**Remote source guard:** If the target source was resolved via GitHub API (remote URL, not a local file path), skip this CCC subsection — CCC requires a local source index and cannot operate on remote-only sources. Note: "CCC semantic discovery skipped — target is remote. CCC discovery will run automatically during create-skill after the source is cloned."

If `tools.ccc` is true in forge-tier.yaml, supplement the module listing with a semantic discovery pass:

**CCC Semantic Discovery:**
- **Claude Code:** Use `/ccc search "{repo_name} public API exports modules" {source_path}`
- **Cursor:** Use `ccc` MCP server `search` tool with query `"{repo_name} public API exports modules"` and path `{source_path}`
- **CLI fallback:** `ccc search "{repo_name} public API exports modules" --path {source_path} --limit 10`

See `knowledge/tool-resolution.md` for full bridge-to-tool mapping.

If results are returned, display:

"**Semantic Signals (ccc):**
{numbered list of file:snippet pairs from CCC results — top 5 most relevant}"

This supplements — never replaces — the explicit module list above. CCC may surface non-obvious entry points (dynamically constructed exports, re-export chains) that static directory analysis misses.

If CCC is unavailable or returns no results: skip this subsection silently.

### 4b. Detect Source Version

**When the language was script-supported (§4 took the script path):** the `version` field returned by `{extractPublicApiHelper}` IS the detected version — do not re-derive it and do not load `{versionResolutionFile}`. The script already implements the language-specific lookups documented in that reference, so loading the reference here only burns context.

**When the language was not script-supported:** load `{versionResolutionFile}` and follow the prose Detection Algorithm directly (Ruby / C# / Swift / etc. fall outside the script's coverage).

Surface the result regardless of which path produced it:

**If `target_version` was provided in step 01:**
- Display: "**Target version:** {target_version} (user-specified)"

Display: "**Detected version:** {version or 'Not detected — will default to 1.0.0'}"

{If target_version was provided AND auto-detected version differs:}
"**Note:** Detected version ({detected_version}) differs from your target version ({target_version}). Using target version (per `references/version-resolution.md` precedence rules)."

If detection fails or returns a non-semver value: note that version will default to `"1.0.0"` and the user can override in step 04. The actual write happens in step 05.

### 5. Report Analysis Summary

Present the complete analysis:

"**Analysis Complete**

---

**Target:** {repo URL or path}
**Language:** {detected language} ({confidence})
**Structure:** {file count} files across {directory count} directories

**Key Modules ({count}):**
{bulleted list of modules}

**Public Exports/Entry Points ({count}):**
{bulleted list of exports}

**Notable Files:**
- README: {found/not found}
- Tests: {found/not found — location}
- Docs: {found/not found — location}
- Config: {list of config files found}
- Version: {detected version or "Not detected — defaulting to 1.0.0"}
{If the target was a GitHub URL:}
- Analysis ref: {analysis_ref} {append " (resolved from target_version {target_version})" when a tag was matched, or " (no tag matched {target_version} — analyzed default branch)" on the zero-match fallback}

Store `{analysis_ref}` in workflow context — step 03 (`scope-definition.md`) reuses it for any further `contents/` fetches so scope analysis reads the same ref as this step.

---

{If language confidence is low:}
**Note:** Language detection confidence is low. You'll be able to override this in the next step.

Moving to scope definition where you'll choose what to include and exclude."

### 6. Auto-Proceed to Scope Definition

Display: "**Proceeding to scope definition...**

Review the analysis above. If anything looks wrong, let me know now — otherwise I'll proceed to scope definition."

Pause briefly for user input. If the user provides corrections or asks questions, address them and re-present any updated analysis findings. Then proceed.

#### Menu Handling Logic:

- After analysis report is presented to user and any corrections addressed, load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is a soft auto-proceed step — present the pause prompt, wait briefly for user input
- If user provides corrections: address them, then proceed
- If no user input after a brief pause: proceed directly to step 03

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the analysis is complete and the summary has been presented to the user will you load and read fully `scope-definition.md` to begin scope definition.


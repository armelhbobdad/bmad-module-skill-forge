---
nextStepFile: './step-03-scope-definition.md'
versionResolutionFile: 'references/version-resolution.md'
extractPublicApiScript: '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

# Step 2: Analyze Target

## STEP GOAL:

To analyze the target repository by resolving its location, reading its structure, detecting the primary language, and listing top-level modules and exports — providing the user with a factual foundation for scoping decisions.

## Rules

- Focus only on analysis — do not define scope yet (Step 03)
- Do not make scoping decisions or recommendations
- Do not hallucinate or guess about repository contents
- All user-facing output in `{communication_language}`

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Resolve Target Location

**For GitHub URLs:**
- Use `gh api repos/{owner}/{repo}` to verify the repository exists
- Use `gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1` to get the file tree

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

Distinguish the failure class before reporting:
- Auto-run `gh auth status` and capture its output. If it reports an unauthenticated state or expired token: HALT (exit code 3, `halt_reason: "gh-auth-failed"`) — "**Error:** GitHub CLI is not authenticated. `gh auth status` says: `{captured output}`. Run `gh auth login` and retry."
- If `gh auth status` reports authenticated but the call still failed (404/403): HALT (exit code 3, `halt_reason: "target-inaccessible"`) — "**Error:** Cannot access repository at `{url}`. The CLI is authenticated but the API returned `{status}`. Check the URL and that the account has access to private repositories if applicable."
- If `gh auth status` itself fails to run (binary missing): HALT (exit code 3, `halt_reason: "gh-auth-failed"`) — "**Error:** `gh` CLI not found on PATH. Install it from <https://cli.github.com> and re-run."

**For local paths:**
- Verify the directory exists
- List the directory tree
- If path doesn't exist: **HALT** — "**Error:** Directory not found at {path}. Verify the path is correct."

Display: "**Resolving target...**"

### 1b. Detect Monorepo / Workspace Layout

Before listing the structure, check whether the root manifest declares a workspace layout:

- **JavaScript/TypeScript:** root `package.json` has a `"workspaces"` array, OR a `pnpm-workspace.yaml` / `lerna.json` exists at the root.
- **Rust:** root `Cargo.toml` has `[workspace]` with a `members = [...]` list.
- **Python:** repo contains multiple `pyproject.toml` under `packages/*/` or `apps/*/`.
- **Generic:** top-level `apps/`, `packages/`, `code/`, or `libs/` directory each containing manifests.

If a workspace layout is detected, list the discovered workspaces and ask:

```
This looks like a monorepo with these workspaces:
  1. {workspace_name} ({path})
  2. {workspace_name} ({path})
  ...
Which one should the skill cover? Pick a number, type 'all' to scope at the repo root, or 'list' to keep listing more.
```

Interactive: wait for the user choice. On a numbered choice, store `monorepo_workspace: {path}` and rebase §2-§4b against that path. On `'all'`, leave `monorepo_workspace` unset and proceed at the repo root with a note in the analysis summary that scope is unfiltered.

Headless: if the input contract supplied an `include` glob that begins with one of the workspace paths, auto-select that workspace (log `"headless: auto-selected workspace {name} from include glob"`). Otherwise default to repo root and log `"warn: monorepo detected but no workspace pre-selected — analyzing at repo root"`.

If no workspace layout is detected, skip this section silently.

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

Examine file extensions and configuration files to detect the primary language:

**Detection signals (check in order):**
1. `package.json` → JavaScript/TypeScript
2. `tsconfig.json` → TypeScript
3. `Cargo.toml` → Rust
4. `pyproject.toml` or `setup.py` or `setup.cfg` → Python
5. `go.mod` → Go
6. `pom.xml` or `build.gradle` → Java
7. `*.csproj` or `*.sln` → C#
8. `Gemfile` → Ruby
9. File extension frequency analysis as fallback

"**Detected language:** {language}
**Confidence:** {high/medium/low}
**Detection source:** {what config file or pattern confirmed it}"

If confidence is low or ambiguous: flag for user override in step 03.

### 4. List Top-Level Modules and Exports

Identify the public API surface. **Delegate the parsing to `{extractPublicApiScript}` whenever the detected language is supported** — the script is the single source of truth for manifest parsing, export discovery, and version detection across the whole SKF pipeline. Hand-rolling these in prose creates drift seams the LLM cannot fully close.

**Script-supported languages** (use the script): `js`, `ts`, `javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`.

This section runs exactly one of §4.1 (script path) or §4.2 (fallback path) based on the detected language, then always emits §4.3 (output format) and conditionally §4.4 (semantic signals).

#### 4.1 Procedure — script-supported languages

1. Read the relevant files into memory (no parsing yet — just collect content). For GitHub sources use `gh api repos/{owner}/{repo}/contents/{file}` with base64 decode; for local sources read directly.

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
   echo '<payload-json>' | uv run {extractPublicApiScript} --language <lang> --mode quick
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

Load `{versionResolutionFile}` for the canonical precedence and invariant rules.

**When the language was script-supported (§4 took the script path):** the `version` field returned by `{extractPublicApiScript}` IS the detected version — do not re-derive it. The script already implements the language-specific lookups documented in `{versionResolutionFile}`.

**When the language was not script-supported:** follow the prose Detection Algorithm in `{versionResolutionFile}` directly (Ruby / C# / Swift / etc. fall outside the script's coverage).

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

ONLY WHEN the analysis is complete and the summary has been presented to the user will you load and read fully `./step-03-scope-definition.md` to begin scope definition.


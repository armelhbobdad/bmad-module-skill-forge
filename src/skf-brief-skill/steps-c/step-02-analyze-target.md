---
nextStepFile: './step-03-scope-definition.md'
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
- If path doesn't exist: **HALT** — "**Error:** Directory not found at {path}. Please verify the path is correct."

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

Based on detected language, identify public API surface:

**For JavaScript/TypeScript:**
- Check `package.json` for `main`, `exports`, `module` fields
- Look for `index.ts`/`index.js` in `src/`
- List directories under `src/` as potential modules

**For Python:**
- Check `__init__.py` files for public exports
- List top-level packages under the source directory

**For Rust:**
- Check `lib.rs` for `pub mod` declarations
- List modules from `src/` directory

**For other languages:**
- List top-level source directories as potential modules
- Note any obvious entry points

"**Top-Level Modules/Directories:**
{numbered list of modules with brief description of each}

**Detected Exports/Entry Points:**
{numbered list of public-facing items found}"

**Semantic Signals (Forge+ and Deep with ccc only):**

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

**If `target_version` was provided in step 01:**
- Display: "**Target version:** {target_version} (user-specified)"
- Still run auto-detection below for informational purposes.

Attempt to auto-detect the source version using the rules from the skill-brief-schema.md Version Detection section:

**For Python:** Check `pyproject.toml` `[project] version` (static) → if `dynamic = ["version"]`, check `__init__.py` for `__version__` → `_version.py` if exists → `setup.py` `version=` → `git describe --tags --abbrev=0`
**For JavaScript/TypeScript:** Check root `package.json` `"version"` field → if root has `"private": true` with a `"workspaces"` array or lacks a `"version"` field, fall back to a primary workspace package's `package.json` (e.g., `code/core/package.json`, or the first matching `packages/*/package.json`). For GitHub sources, prefer `gh api repos/{owner}/{repo}/releases/latest` → `tag_name` when a non-pre-release tag exists, over a default-branch pre-release. Treat a version containing `-alpha`, `-beta`, `-rc`, `-next`, or `-canary` as a pre-release.
**For Rust:** Check `Cargo.toml` `[package] version` (static) → if `version = { workspace = true }`, resolve from workspace root `Cargo.toml` → `git describe --tags --abbrev=0`
**For Go:** Check `go.mod` or `git describe --tags --abbrev=0`

**For GitHub repos:** Use `gh api repos/{owner}/{repo}/contents/{file}` to read version files (decode base64 content).
**For local repos:** Read the file directly.

Display: "**Detected version:** {version or 'Not detected — will default to 1.0.0'}"

{If target_version was provided AND auto-detected version differs:}
"**Note:** Detected version ({detected_version}) differs from your target version ({target_version}). Using target version."

{If target_version was provided:}
Store `target_version` as the brief's `version` field (overrides auto-detection).

If detection fails or returns a non-semver value: note that version will default to `"1.0.0"` and the user can override in step 04.

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


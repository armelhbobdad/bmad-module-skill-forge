# Source Resolution Protocols

## Tag Resolution

Tag resolution maps a declared version in the brief onto a concrete git ref before cloning, so the skill is built from code matching its declared version. Two paths trigger tag resolution: an **explicit** `brief.target_version` (deliberate user intent) or an **implicit** `brief.version` (auto-populated hint from `brief-skill`). Both apply only when `source_repo` is a remote URL.

**When neither `brief.target_version` nor `brief.version` is set:** skip tag resolution entirely. Set `source_ref` to `HEAD` (default branch).

### Explicit Tag Resolution (when target_version is set)

When `brief.target_version` is present AND `source_repo` is a remote URL, resolve the target version to a git tag before cloning:

1. **List available tags:**
   - `gh api repos/{owner}/{repo}/tags --paginate --jq '.[].name'`
   - Fallback: `git ls-remote --tags {source_repo} | sed 's|.*refs/tags/||'`

2. **Match `target_version` against tags** in priority order:
   - **Exact match:** `{target_version}` (e.g., `0.5.0`)
   - **With `v` prefix:** `v{target_version}` (e.g., `v0.5.0`)
   - **With package scope (monorepos):** `{brief.name}@{target_version}` or `@{scope}/{brief.name}@{target_version}`

3. **Resolution outcomes:**
   - **Single match:** Store the matched tag as `source_ref`. Use it as `{branch}` in all subsequent clone/API commands.
   - **Multiple matches:** Present the matching tags to the user — "Multiple tags match version {target_version}: {list}. Which one should I use?" Wait for selection.
   - **Zero matches:** ⚠️ Warn: "No git tag found matching version {target_version}. Closest available tags: {list 5 nearest by semver sort}. Falling back to default branch — **extracted code may not match target version.**" Set `source_ref` to `HEAD` and proceed with default branch.

4. **Store `source_ref`** in context. This value is written to metadata.json and provenance-map.json for downstream workflows (update-skill, audit-skill) to re-clone from the same ref.

### Implicit Tag Resolution (when only brief.version is set)

When `brief.target_version` is absent but `brief.version` is present AND `source_repo` is a remote URL, treat `brief.version` as an **implicit** target version and attempt tag resolution before cloning. This matches `brief-skill`'s behavior, which auto-populates `brief.version` from the latest non-prerelease release tag — so a tag matching `brief.version` is the common case, and silently cloning HEAD would produce a skill labeled with `brief.version` but built from an unrelated default-branch commit.

1. **List available tags** exactly as in Explicit Tag Resolution above.

2. **Match `brief.version` against tags** in this reduced priority order. Package-scoped monorepo variants are **not** tried — those require deliberate user intent via `target_version`, since implicit matching against a monorepo tag like `{brief.name}@{version}` could silently select a sibling package's ref:
   - **Exact match:** `{brief.version}` (e.g., `0.3.37`)
   - **With `v` prefix:** `v{brief.version}` (e.g., `v0.3.37`)

3. **Resolution outcomes:**
   - **Single match:** Store the matched tag as `source_ref`. Use it as `{branch}` in all subsequent clone/API commands. Do not warn — this is the expected path.
   - **Multiple matches:** Present the matching tags to the user — "Multiple tags match `brief.version` ({brief.version}): {list}. Which one should I use, or fall back to HEAD?" Wait for selection.
   - **Zero matches:** ⚠️ Warn: "No git tag found matching `brief.version` ({brief.version}). Falling back to default branch — **extracted code may not match the declared version.** If you intended to pin a specific version, set `target_version` explicitly in the brief." Set `source_ref` to `HEAD` and proceed with default branch.

4. **Do not halt on zero matches.** Unlike the explicit path, implicit resolution never blocks compilation — `brief.version` is an auto-populated hint, and some repositories simply do not tag releases. The warning is sufficient notice; the evidence report in step-08 will surface the HEAD fallback for reviewers.

5. **Store `source_ref`** in context exactly as in the explicit path. It flows through to metadata.json and provenance-map.json so downstream workflows (update-skill, audit-skill) can re-clone from the same ref.

**Interaction with Version Reconciliation (below):** When implicit tag resolution succeeds, the clone's source files should carry the same version as `brief.version` — so the Version Reconciliation section's source-vs-brief mismatch warning will not fire. When implicit resolution falls back to HEAD, Version Reconciliation runs normally against the default branch's version file and may produce its own mismatch warning.

### Local Source Warning

When `brief.target_version` is set AND `source_repo` is a local path:

⚠️ "**Local source may not match target version {target_version}.** Ensure you've checked out the correct version locally, or use a remote GitHub URL so SKF can clone from the git tag automatically."

Proceed with local files as-is. Set `source_ref` to `"local"`.

Implicit resolution via `brief.version` is **not applied to local sources** — local paths reflect whatever the user has checked out, and rewriting them from a tag would be out of scope for a local-source workflow.

---

## Remote Source Resolution

**Note:** Quick-tier remote sources do not use the workspace/clone protocol described below. Quick tier accesses remote files via the `gh_bridge.read_file` path described in step-03 section 4.

If `source_repo` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_repo` is a remote URL (GitHub URL or owner/repo format) AND tier is Forge, Forge+, or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Compute workspace path:** Derive a persistent local path from the remote URL:

   - **Parse the URL** to extract `{host}`, `{owner}`, `{repo}`:
     - `https://github.com/facebook/react` or `https://github.com/facebook/react.git` → `github.com/facebook/react`
     - `git@github.com:facebook/react.git` → `github.com/facebook/react`
     - `facebook/react` (owner/repo shorthand) → `github.com/facebook/react`
   - **Resolve workspace root:** Use environment variable `SKF_WORKSPACE` if set, otherwise `~/.skf/workspace/` (where `~` is the user's home directory on all platforms)
   - **Workspace repo path:** `{workspace_root}/repos/{host}/{owner}/{repo}/`

3. **Workspace check — resolve the source locally:**

   **If `{workspace_repo_path}/.git/` exists (workspace hit):**

   The repo was previously cloned into the workspace. Fetch updates and checkout the requested ref:

   ```
   git -C {workspace_repo_path} fetch origin {source_ref}
   ```

   Check if checkout is needed — skip if the requested ref is already checked out:

   ```
   current_head = git -C {workspace_repo_path} rev-parse HEAD
   fetched_head = git -C {workspace_repo_path} rev-parse FETCH_HEAD
   ```

   If `current_head != fetched_head`:
   ```
   git -C {workspace_repo_path} -c advice.detachedHead=false checkout FETCH_HEAD
   ```

   If fetch or checkout fails, proceed to the **ephemeral fallback** (step 5).

   **If `{workspace_repo_path}/.git/` does NOT exist (workspace miss):**

   Clone the repository into the workspace for persistent reuse. Create the parent directory first (`{workspace_root}/repos/{host}/{owner}/`):

   ```
   mkdir -p "{workspace_root}/repos/{host}/{owner}/"
   ```

   Clone with the appropriate branch flag — `--branch` is only valid for real branch/tag names, not for `HEAD`:

   ```
   # If source_ref is a real branch or tag (not HEAD/null):
   git clone --depth 1 --branch {source_ref} --single-branch {source_repo} {workspace_repo_path}

   # If source_ref is HEAD or not set (default branch):
   git clone --depth 1 --single-branch {source_repo} {workspace_repo_path}
   ```

   **Note:** No `--filter=blob:none` — blobs for the current tree are needed for indexing and the cost is amortized across all future forges. No sparse-checkout — a full checkout serves all consumers (different briefs with different include/exclude patterns) without configuration conflicts.

   If this is the **first repo** in the workspace (workspace root was just created), print an informational message:

   "Caching source at `{workspace_repo_path}` (saves time on re-forges). Override location with `SKF_WORKSPACE` env var."

   If clone fails, proceed to the **ephemeral fallback** (step 5).

4. **If workspace resolution succeeds:** Set `source_root = {workspace_repo_path}` — this updates the working source path for all subsequent operations (AST extraction, CCC indexing, artifact generation). Capture the source commit: `git -C {workspace_repo_path} rev-parse HEAD` — store as `source_commit` in context. Proceed with the **Forge/Deep Tier** extraction strategy below. Set context:
   - `source_root = {workspace_repo_path}`
   - `remote_clone_path = {workspace_repo_path}`
   - `remote_clone_type = "workspace"`

   **Scope filtering:** Since the workspace uses a full checkout (no sparse-checkout), apply `include_patterns` and `exclude_patterns` from the brief as **file-level filters** when building the extraction file list. Always-included root files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `setup.py`, `setup.cfg`, `VERSION`) are exempt from pattern filtering.

5. **Ephemeral fallback (on any workspace failure):**

   If workspace clone or fetch fails for any reason (network error, auth failure, disk full, timeout), fall back to ephemeral cloning — the pre-workspace behavior that always works:

   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/

   # If source_ref is a real branch or tag (not HEAD/null):
   git clone --depth 1 --branch {source_ref} --single-branch --filter=blob:none {source_repo} {temp_path}

   # If source_ref is HEAD or not set (default branch):
   git clone --depth 1 --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   If ephemeral clone succeeds: Set `source_root = {temp_path}`. Capture `source_commit`. Set context:
   - `source_root = {temp_path}`
   - `remote_clone_path = {temp_path}`
   - `remote_clone_type = "ephemeral"`

   Apply `include_patterns` and `exclude_patterns` from the brief as file-level filters when building the extraction file list.

6. **If all cloning fails (workspace AND ephemeral):**

   ⚠️ **Warn the user explicitly:**

   "Clone of `{source_repo}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path."

   Proceed with Quick tier extraction strategy below. Note the degradation reason in context for the evidence report.

**Remote clone cleanup:** After extraction is complete for all files in scope (whether successful or partially failed), before presenting the Gate 2 summary (Section 6):

- **If `remote_clone_type == "ephemeral"`:** Cleanup is required.
  1. **Reset working directory first:** Run `cd {project-root}` using the **absolute path** captured at workflow start.
  2. **Delete the clone:** `rm -rf {temp_path}`
  3. **Log:** "Ephemeral source clone cleaned up."

  This ensures cleanup runs even if some extractions failed. If any error halts the step before Gate 2, cleanup must still occur.

- **If `remote_clone_type == "workspace"`:** No cleanup. The workspace checkout persists for future forges.

---

## Source Commit Capture (all tiers, source mode only)

**If `source_type: "docs-only"`:** skip — set `source_commit: null`.

After the source path is accessible, capture the current commit hash for provenance tracking:

- **Local path:** `git -C {source_root} rev-parse HEAD` — if the path is a git repo
- **Ephemeral clone (Forge/Deep):** already captured during clone (step 3 above)
- **Quick tier (remote, no clone):** `gh api repos/{owner}/{repo}/commits/{source_ref} --jq '.sha'`

Store the result as `source_commit` in context. If capture fails (not a git repo, API unavailable), set `source_commit: null` — this is not an error.

Also store `source_ref` in context (from tag resolution above, or `HEAD` if no tag was resolved, or `"local"` for local sources). This value is persisted to metadata.json and provenance-map.json so downstream workflows (update-skill, audit-skill) can re-access the same source ref.

---

## Version Reconciliation (all tiers, source mode only)

**Target version override:** If `brief.target_version` is present, use it as the authoritative version for the skill. Do NOT warn about a brief-vs-source version mismatch — the user intentionally specified this version. Set the working version to `brief.target_version` and skip the rest of this reconciliation section. The `target_version` field indicates deliberate user intent (e.g., targeting an older version, or providing the version for a docs-only skill).

**If `source_type: "docs-only"`:** skip this section — no source files exist to reconcile.

After the source path is accessible (local path from step-01, or workspace/ephemeral clone from above), check whether the source contains a version identifier and reconcile it with `brief.version`. Look for the first matching version file in the resolved source path:

- Python: `pyproject.toml` (`[project] version`), `setup.py` (`version=`), `__version__` in `__init__.py`
- JavaScript/TypeScript: `package.json` (`"version"`). **Monorepo resolution:** When multiple `package.json` files exist (workspace root + packages), resolve version using this priority:
  1. Package whose `name` field matches `brief.name` (e.g., the skill's target library name)
  2. Package with a `bin` field (CLI entry point — represents the published version)
  3. Root workspace `package.json` version (if present)
  4. Fall back to `brief.version` if no version found. For monorepos using workspace protocols (pnpm, yarn, npm workspaces), the root `package.json` often has no `version` field — this is expected, not an error.
- Rust: `Cargo.toml` (`[package] version`)
- Go: `go.mod` (module version if tagged)

**If a source version is found AND it differs from `brief.version`:**

⚠️ Warn the user: "Brief version ({brief.version}) differs from source version ({source_version}). Using source version ({source_version})."

Update the working version in context to the source version. Record the mismatch in context for the evidence report (step-08).

**If no version file is found or version cannot be extracted:** keep `brief.version` as-is. No warning needed.

**If source is remote and accessed via Quick tier (gh_bridge, no local files):** attempt to read the version file via `gh_bridge.read_file(owner, repo, "{version_file}")` — resolved as `gh api repos/{owner}/{repo}/contents/{version_file}` or direct file read if local (see `knowledge/tool-resolution.md`) — for the primary version file of the detected language. If the read fails, keep `brief.version`.

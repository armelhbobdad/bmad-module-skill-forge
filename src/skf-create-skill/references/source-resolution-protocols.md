# Source Resolution Protocols

## Tag Resolution (when target_version is set)

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

When `brief.target_version` is NOT set: skip tag resolution. Set `source_ref` to `HEAD` (default branch behavior, unchanged from before).

### Local Source Warning

When `brief.target_version` is set AND `source_repo` is a local path:

⚠️ "**Local source may not match target version {target_version}.** Ensure you've checked out the correct version locally, or use a remote GitHub URL so SKF can clone from the git tag automatically."

Proceed with local files as-is. Set `source_ref` to `"local"`.

---

## Remote Source Resolution (Forge/Deep only)

If `source_repo` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_repo` is a remote URL (GitHub URL or owner/repo format) AND tier is Forge or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Ephemeral shallow clone:** Clone the repository to a system temp path for AST access. Use `source_ref` from tag resolution (or `{branch}` for the default branch if no tag was resolved):

   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/
   git clone --depth 1 --branch {source_ref} --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   **If `include_patterns` are NOT specified:**

   ```
   git clone --depth 1 --branch {source_ref} --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   **If `include_patterns` ARE specified**, use sparse-checkout to limit the clone scope:

   ```
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none --sparse {source_repo} {temp_path}
   ```

   **Mode selection:** Choose sparse-checkout mode based on whether `exclude_patterns` exist:

   - **No `exclude_patterns`:** Use default **cone mode** (faster). Convert `include_patterns` to directory roots.
   - **`exclude_patterns` present:** Use **`--no-cone` mode** which supports gitignore-style negation patterns (`!` prefix). This applies both include and exclude at the git level, avoiding unnecessary blob downloads.

   **Cone mode (no exclude patterns):**

   **IMPORTANT:** `git sparse-checkout set` expects **directories**, not glob patterns. Convert `include_patterns` before passing them:

   **Classification rule:** A pattern is an **individual file** if it contains no glob characters (`*`, `?`, `[`) AND does not end with `/`. Everything else is a glob — strip it to its directory root (the path prefix before the first glob character or wildcard segment).

   - Strip glob suffixes to directory roots (e.g., `src/core/**/*.py` → `src/core`, `src/api/*.ts` → `src/api`)
   - Deduplicate the resulting directory list
   - Individual files (e.g., `pyproject.toml`, `src/utils/helpers.py`) are kept as-is

   **If only directory roots (no individual files):**

   ```
   git -C {temp_path} sparse-checkout set {converted_directory_roots}
   ```

   **If any individual files are present (or mixed):**

   ```
   git -C {temp_path} sparse-checkout set --skip-checks {converted_directory_roots} {individual_files}
   ```

   Example transformation:
   ```
   Brief include_patterns:        sparse-checkout args:
   src/core/**/*.py          →    src/core          (directory root)
   src/api/*.ts              →    src/api           (directory root)
   examples/**/*.py          →    examples          (directory root)
   pyproject.toml            →    pyproject.toml    (individual file, needs --skip-checks)
   src/utils/helpers.py      →    src/utils/helpers.py (individual file, needs --skip-checks)
   ```

   **No-cone mode (exclude patterns present):**

   When `exclude_patterns` exist, use `--no-cone` mode to pass both include and exclude patterns directly as gitignore-style rules:

   1. Convert `include_patterns` to gitignore-style patterns. For patterns without glob characters (`*`, `?`, `[`) that do not end with `/`, apply the **file-detection heuristic**: if the last path segment contains a `.` (file extension), it is an **individual file** — prepend `/` and keep as-is (e.g., `packages/registry/registry.json` → `/packages/registry/registry.json`). If the last path segment has no extension, it is a **bare directory name** — append `/**` (e.g., `cognee` → `cognee/**`). Patterns that already contain glob characters are kept as-is (e.g., `cognee/**` → kept as-is).
   2. Convert `exclude_patterns` to negation patterns by prepending `!`. Apply the same file-detection heuristic: individual files (last segment has `.` extension) get `!/` prefix only (e.g., `src/internal/config.json` → `!/src/internal/config.json`); bare directory names get `/**` appended (e.g., `cognee/tests` → `!cognee/tests/**`). Patterns with globs are kept as-is with `!` prefix (e.g., `cognee/tests/**` → `!cognee/tests/**`; `**/test_*` → `!**/test_*`).
   3. **CRITICAL:** List all include patterns BEFORE negated exclude patterns — git processes patterns in order and a negation can only suppress a prior inclusion.
   4. Pass to sparse-checkout — include patterns first, then negated exclude patterns:

   ```
   git -C {temp_path} sparse-checkout set --no-cone {include_gitignore_patterns} {negated_exclude_patterns}
   ```

   Example transformation:
   ```
   Brief include_patterns:          Brief exclude_patterns:
   cognee/**                        cognee/tests/**
   packages/registry/registry.json  cognee/alembic/**
                                    **/test_*

   sparse-checkout args (--no-cone):
   'cognee/**' '/packages/registry/registry.json' '!cognee/tests/**' '!cognee/alembic/**' '!**/test_*'
   ```

   Note: `registry.json` is an individual file (has `.json` extension), so it gets `/` prefix instead of `/**` suffix.

   **Note:** `--no-cone` mode is slower than cone mode for very large repositories but eliminates downloading excluded blobs entirely.

   **Always-included root files:**

   Regardless of `include_patterns`, always add these root-level version/manifest files to the sparse-checkout pattern list. These are needed for version reconciliation and must not require a fallback to `gh api`:

   `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `setup.py`, `setup.cfg`, `VERSION`

   In cone mode, always use the `--skip-checks` command form when adding these files — even if `include_patterns` resolved to only directory roots (which would normally use the form without `--skip-checks`). The command becomes: `git -C {temp_path} sparse-checkout set --skip-checks {directory_roots} pyproject.toml package.json Cargo.toml go.mod setup.py setup.cfg VERSION`. In no-cone mode, list them as explicit include patterns before any negation patterns. Do not flag them as extraneous inclusions during post-checkout filtering.

   **Post-checkout filtering:**

   After checkout, apply the original glob `include_patterns` as file-level filters when building the extraction file list — sparse-checkout gets the right directories, glob filtering narrows to the exact files. When `--no-cone` mode was used, most exclude filtering is already done at the git level, but apply `exclude_patterns` as a final pass to catch any edge cases where gitignore pattern matching diverges from the brief's glob semantics. Always-included root files (see above) are exempt from post-checkout filtering.

3. **If clone succeeds:** Update the working source path to `{temp_path}` for all subsequent AST operations in this step. Capture the source commit: `git -C {temp_path} rev-parse HEAD` — store as `source_commit` in context. Proceed with the **Forge/Deep Tier** extraction strategy below. Mark `ephemeral_clone_active = true` for cleanup.

4. **If clone fails (network error, auth failure, timeout):**

   ⚠️ **Warn the user explicitly:**

   "Ephemeral clone of `{source_repo}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path."

   Proceed with Quick tier extraction strategy below. Note the degradation reason in context for the evidence report.

**Ephemeral clone cleanup:** After extraction is complete for all files in scope (whether successful or partially failed), before presenting the Gate 2 summary (Section 6), if `ephemeral_clone_active`:

1. **Reset working directory first:** Before deleting the clone, ensure the shell working directory is not inside the temp path. Run `cd {project-root}` using the **absolute path** captured at workflow start (not a relative path). This prevents `getcwd` errors when the temp directory is deleted while it is the shell's cwd — which happens if `cd {temp_path}` was used during CCC init or extraction operations.
2. **Delete the clone:** `rm -rf {temp_path}`
3. **Log:** "Ephemeral source clone cleaned up."

This ensures cleanup runs even if some extractions failed, as long as the step itself is still executing. **If any error halts the extraction step before Gate 2 is reached**, cleanup must still occur: reset cwd to `{project-root}` and attempt to delete `{temp_path}` before halting. Log the cleanup attempt regardless of success.

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

After the source path is accessible (local path from step-01, or ephemeral clone from above), check whether the source contains a version identifier and reconcile it with `brief.version`. Look for the first matching version file in the resolved source path:

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

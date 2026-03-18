# Source Resolution Protocols

## Remote Source Resolution (Forge/Deep only)

If `source_repo` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_repo` is a remote URL (GitHub URL or owner/repo format) AND tier is Forge or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Ephemeral shallow clone:** Clone the repository to a system temp path for AST access:

   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   **If `include_patterns` are NOT specified:**

   ```
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none {source_repo} {temp_path}
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

   1. Convert `include_patterns` to gitignore-style patterns. If a pattern contains no glob characters (`*`, `?`, `[`) and does not end with `/`, append `/**` to match directory contents recursively (e.g., `cognee` → `cognee/**`; `cognee/**` → kept as-is).
   2. Convert `exclude_patterns` to negation patterns by prepending `!`. Apply the same anchoring rule (e.g., `cognee/tests` → `!cognee/tests/**`; `cognee/tests/**` → `!cognee/tests/**`; `**/test_*` → `!**/test_*`).
   3. **CRITICAL:** List all include patterns BEFORE negated exclude patterns — git processes patterns in order and a negation can only suppress a prior inclusion.
   4. Pass to sparse-checkout — include patterns first, then negated exclude patterns:

   ```
   git -C {temp_path} sparse-checkout set --no-cone {include_gitignore_patterns} {negated_exclude_patterns}
   ```

   Example transformation:
   ```
   Brief include_patterns:        Brief exclude_patterns:
   cognee/**                      cognee/tests/**
                                  cognee/alembic/**
                                  **/test_*

   sparse-checkout args (--no-cone):
   'cognee/**' '!cognee/tests/**' '!cognee/alembic/**' '!**/test_*'
   ```

   **Note:** `--no-cone` mode is slower than cone mode for very large repositories but eliminates downloading excluded blobs entirely.

   **Post-checkout filtering:**

   After checkout, apply the original glob `include_patterns` as file-level filters when building the extraction file list — sparse-checkout gets the right directories, glob filtering narrows to the exact files. When `--no-cone` mode was used, most exclude filtering is already done at the git level, but apply `exclude_patterns` as a final pass to catch any edge cases where gitignore pattern matching diverges from the brief's glob semantics.

3. **If clone succeeds:** Update the working source path to `{temp_path}` for all subsequent AST operations in this step. Proceed with the **Forge/Deep Tier** extraction strategy below. Mark `ephemeral_clone_active = true` for cleanup.

4. **If clone fails (network error, auth failure, timeout):**

   ⚠️ **Warn the user explicitly:**

   "Ephemeral clone of `{source_repo}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path."

   Proceed with Quick tier extraction strategy below. Note the degradation reason in context for the evidence report.

**Ephemeral clone cleanup:** After extraction is complete for all files in scope (whether successful or partially failed), before presenting the Gate 2 summary (Section 6), if `ephemeral_clone_active`, delete the `{temp_path}` directory. Log: "Ephemeral source clone cleaned up." This ensures cleanup runs even if some extractions failed, as long as the step itself is still executing.

---

## Version Reconciliation (all tiers, source mode only)

**If `source_type: "docs-only"`:** skip this section — no source files exist to reconcile.

After the source path is accessible (local path from step-01, or ephemeral clone from above), check whether the source contains a version identifier and reconcile it with `brief.version`. Look for the first matching version file in the resolved source path:

- Python: `pyproject.toml` (`[project] version`), `setup.py` (`version=`), `__version__` in `__init__.py`
- JavaScript/TypeScript: `package.json` (`"version"`)
- Rust: `Cargo.toml` (`[package] version`)
- Go: `go.mod` (module version if tagged)

**If a source version is found AND it differs from `brief.version`:**

⚠️ Warn the user: "Brief version ({brief.version}) differs from source version ({source_version}). Using source version ({source_version})."

Update the working version in context to the source version. Record the mismatch in context for the evidence report (step-08).

**If no version file is found or version cannot be extracted:** keep `brief.version` as-is. No warning needed.

**If source is remote and accessed via Quick tier (gh_bridge, no local files):** attempt to read the version file via `gh_bridge.read_file(owner, repo, "{version_file}")` for the primary version file of the detected language. If the read fails, keep `brief.version`.

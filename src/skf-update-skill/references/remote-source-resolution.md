# Remote Source Resolution (Forge/Deep Tier)

If `source_root` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_root` (from metadata.json) is a remote URL (GitHub URL or owner/repo format) AND tier is Forge or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Resolve source ref:** Read `source_ref` from the existing `metadata.json`. If the user provided a new `target_version`, resolve its tag first (using the Tag Resolution algorithm in `create-skill/references/source-resolution-protocols.md`).

3. **Workspace check:** Compute the workspace path using the same algorithm as `create-skill/references/source-resolution-protocols.md` (parse URL → `{workspace_root}/repos/{host}/{owner}/{repo}/`).

   **If workspace repo exists (`{workspace_repo_path}/.git/` present):**

   Fetch and checkout the requested ref. For update-skill, `changed_files_from_manifest` scoping happens at extraction time via file-level filtering — the workspace has a full checkout.

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

   Set `remote_clone_path = {workspace_repo_path}`, `remote_clone_type = "workspace"`.

   **If workspace repo does NOT exist:**

   Clone into workspace. Create the parent directory first:

   ```
   mkdir -p "{workspace_root}/repos/{host}/{owner}/"
   ```

   Clone with the appropriate branch flag — `--branch` is only valid for real branch/tag names, not for `HEAD`:

   ```
   # If source_ref is a real branch or tag (not HEAD/null/"local"):
   git clone --depth 1 --branch {source_ref} --single-branch {source_repo} {workspace_repo_path}

   # If source_ref is HEAD or not set (default branch):
   git clone --depth 1 --single-branch {source_repo} {workspace_repo_path}
   ```

   Set `remote_clone_path = {workspace_repo_path}`, `remote_clone_type = "workspace"`.

   **On any workspace failure:** Fall back to ephemeral clone:
   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/

   # If source_ref is a real branch or tag (not HEAD/null/"local"):
   git clone --depth 1 --branch {source_ref} --single-branch --filter=blob:none {source_root} {temp_path}

   # If source_ref is HEAD or not set (default branch):
   git clone --depth 1 --single-branch --filter=blob:none {source_root} {temp_path}
   ```
   Set `remote_clone_path = {temp_path}`, `remote_clone_type = "ephemeral"`.

4. **If clone/fetch succeeds:** Set `source_root = {remote_clone_path}` — this updates the working source path for all subsequent operations. Apply `changed_files_from_manifest` as file-level filters at extraction time. Proceed with the **Forge tier** extraction strategy below.

5. **If all cloning fails (workspace AND ephemeral):**

   Warning message: "Clone of `{source_root}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and re-run [CS] Create Skill with the local path, then re-run this update."

   Override the extraction strategy to Quick tier for this run. Note the degradation reason in context for the evidence report.

## Remote Clone Cleanup

After extraction is complete for all files in scope (whether successful or partially failed), before presenting the extraction summary:

- **If `remote_clone_type == "ephemeral"`:** Reset the working directory first (`cd {project-root}` using the absolute path captured at workflow start), then delete the `{temp_path}` directory. Log: "Ephemeral source clone cleaned up." This ensures cleanup runs even if some extractions failed.
- **If `remote_clone_type == "workspace"`:** No cleanup. The workspace checkout persists for future forges and updates.

## Version Reconciliation

After the source path is accessible, check whether the source version has changed since the original skill was created. Look for the version file matching the detected language (e.g., `pyproject.toml`, `package.json`, `Cargo.toml`). If the source version differs from the current `metadata.json` version, record `source_version_detected` in context for step-06 to use when updating `metadata.json`. No warning needed here — step-06 handles the version update.

## AST Tool Unavailability (Local Source)

If AST tool is unavailable at Forge/Deep tier with local source:

Warning message: "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

# Remote Source Resolution (Forge/Deep Tier)

If `source_root` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_root` (from metadata.json) is a remote URL (GitHub URL or owner/repo format) AND tier is Forge or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Ephemeral sparse clone:** Clone only the changed files from the change manifest to a system temp path. Note: at this point in the flow, `{source_root}` is known to be a remote URL (the local-path case was already handled above).

   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/
   git clone --depth 1 --single-branch --filter=blob:none --sparse {source_root} {temp_path}
   git -C {temp_path} sparse-checkout set --skip-checks {changed_files_from_manifest}
   ```

   **Note:** `--skip-checks` is required because `changed_files_from_manifest` contains individual file paths (e.g., `src/core/parser.py`), not directories. Without this flag, `git sparse-checkout set` rejects non-directory entries.

   No `--branch` flag is used — the clone targets the remote's default branch, which must match the branch used during the original [CS] Create Skill run. This scopes the clone to only the files identified in step-02's change manifest, avoiding a full repository download.

3. **If clone succeeds:** Update the working source path to `{temp_path}` for all subsequent AST operations in this step. Proceed with the **Forge tier** extraction strategy below. Mark `ephemeral_clone_active = true` for cleanup.

4. **If clone fails (network error, auth failure, timeout):**

   Warning message: "Ephemeral clone of `{source_root}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and re-run [CS] Create Skill with the local path, then re-run this update."

   Override the extraction strategy to Quick tier for this run. Note the degradation reason in context for the evidence report.

## Ephemeral Clone Cleanup

After extraction is complete for all files in scope (whether successful or partially failed), before presenting the extraction summary, if `ephemeral_clone_active`, delete the `{temp_path}` directory. Log: "Ephemeral source clone cleaned up." This ensures cleanup runs even if some extractions failed, as long as the step itself is still executing.

## Version Reconciliation

After the source path is accessible, check whether the source version has changed since the original skill was created. Look for the version file matching the detected language (e.g., `pyproject.toml`, `package.json`, `Cargo.toml`). If the source version differs from the current `metadata.json` version, record `source_version_detected` in context for step-06 to use when updating `metadata.json`. No warning needed here — step-06 handles the version update.

## AST Tool Unavailability (Local Source)

If AST tool is unavailable at Forge/Deep tier with local source:

Warning message: "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

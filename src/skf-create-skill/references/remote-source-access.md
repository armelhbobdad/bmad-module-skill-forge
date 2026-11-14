# Remote Source Access

Step 3 (`extract.md`) §2a loads this file for a remote source at Forge, Forge+ or Deep tier. The keys it names are step 3's frontmatter keys, and a bare § names a section of step 3.

## Read the Source Into a Private Tree

`{sourceTreeHelper}` reads the source into a private tree at one commit, which no other run can move, and in the same call moves SKF's workspace clone of the repository to that commit (`{sourceResolutionData}` "Remote Source Resolution"). Resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`; it stays bound for the rest of the run (step 7 and every HALT use it). Resolve `{cccGitHygieneHelper}` ← first existing path in `{cccGitHygieneProbeOrder}`. Bind `{tree_timeout}` to the seconds the helper may take, a little under the longest timeout your shell tool can be given, since a first fetch of a large repository is slow: `540` when it takes a 10-minute timeout, `100` when its longest is two minutes or you do not know it. Give the command that longest shell timeout: the helper stops itself within `--timeout` seconds and still prints its result. From `{project-root}`, run:

```bash
uv run {sourceTreeHelper} resolve \
    --source-repo "{source_repo}" \
    [--target-ref "{brief.target_ref}"] \
    [--version "{brief.target_version}" --name "{brief.name}"] \
    [--version "{brief.version}" --implicit] \
    --update-clone \
    [--hygiene-helper "{cccGitHygieneHelper}"] \
    --timeout "{tree_timeout}"
```

Pass `--target-ref` when the brief sets `target_ref`. Pass the first `--version` line when the brief sets `target_version`, else the second when it sets `version`, never both. Pass `--hygiene-helper` when `{cccGitHygieneHelper}` resolved.

Bind from its JSON `source_ref` ← `source_ref`, `source_commit` ← `source_commit`, `tag_resolution` ← `tag_resolution`, `{workspace_path}` ← `workspace_path`, `{workspace_clone}` ← `clone`, `{source_tree}` ← `tree`, `{source_resolve_status}` ← `status`, `{source_resolve_reason}` ← `reason`, `{source_resolve_message}` ← `message`, `{clone_status}` ← `clone_status` and `{clone_skip_reason}` ← `clone_skip_reason`, and display each entry of `warnings`.

Dispatch on `{source_resolve_status}`:

- **`ready`** (exit 0): bind `{source_root}` ← `{source_tree}`. Every later read of the source reads this tree: the §2 file list, the §2b scan, extraction, step 6's citation check and step 7's script and asset copies. Build the §2 filtered file list again from `{source_root}` when §2 builds one (a `component-library` brief), since step 1 listed the remote's default branch, which need not hold `source_commit`. Bind `{resolved-source-path}` ← `{workspace_clone}`, or ← `{source_repo}` when `{workspace_clone}` is null (the folder at `{workspace_path}` is not SKF's clone of the repository): it is the `source_root` metadata.json records (`{sourceResolutionData}` "Source Commit Capture"). When `{clone_status}` is `advanced` or `ok`, SKF's clone now holds `source_commit`: bind `{remote_clone_path}` ← `{workspace_clone}`, the folder the deferred ccc discovery below and step 7 §6b index. Otherwise leave it null and display "SKF's clone of `{source_repo}` at `{workspace_path}` was not moved ({clone_skip_reason}), so this run skips ccc discovery and the ccc index registration. Extraction reads this run's own tree." Then report the outcome of `tag_resolution` as `{sourceResolutionData}` "Tag Resolution" says.
- **`ambiguous`** (exit 0): several tags match, and nothing was read. Make the choice in `{sourceResolutionData}` "Several Matching Tags", run the command again with `--target-ref "{chosen tag}"` (`HEAD` for the default branch) in place of `--version`, `--name`, `--implicit` and any `--target-ref` from the brief, and dispatch on that result.
- **`skipped`** (exit 0): the helper does not read `{source_repo}` as a remote repository (`skip_reason` is `not-remote`), so treat it as the local source §2a describes.
- **`unavailable`** (exit 3): no commit could be read, and no tree was left behind (`{source_resolve_reason}` is `invalid-ref`, `git-unavailable`, `upstream-unreachable`, `ref-not-found`, `fetch-failed`, `checkout-failed`, `tree-folder-failed` or `timed-out`). ⚠️ Warn the user explicitly: "Could not read `{source_repo}`: {source_resolve_message}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path." Keep `{source_root}` the remote URL, bind `source_ref` ← `source_ref` when it is not null and `HEAD` otherwise, and extract with the Quick tier strategy in §4. Note the degradation reason in context for the evidence report.
- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:** continue as for `unavailable`, with `{source_resolve_message}` = "skf-source-tree.py did not finish: {the first stderr line; 'the shell stopped it before it printed a result' when your shell tool's timeout ended it; or 'it is missing; re-install SKF'}". A later run removes a tree a stopped run left behind once it is seven days old.

## Deferred CCC Discovery

If ALL of these conditions are true:
- `tools.ccc` is true in forge-tier.yaml
- `{ccc_discovery}` is empty (step 2b deferred because source was remote)
- `{remote_clone_path}` is set (SKF's clone holds `source_commit`)
- Tier is Forge+ or Deep

Then index SKF's clone and search it. The clone persists across forges, so an index an earlier forge built there is brought up to date rather than rebuilt. ccc's results only rank files; extraction still reads `{source_root}`.

1. **Prepare the settings:** resolve `{mergeCccExclusionsHelper}` ← first existing path in `{mergeCccExclusionsProbeOrder}` and, from `{project-root}`, run `uv run {mergeCccExclusionsHelper} --clone-root "{remote_clone_path}"`. It runs `ccc init -f` in the clone when `.cocoindex_code/settings.yml` is missing, and appends the standard build and dependency exclusions the file lacks (`**/node_modules`, `**/dist`, `**/build`, `**/target` and the like), on a first run and on a reused index alike, keeping every entry already there. These are standard artifact patterns, not SKF paths: the clone is a source repository, not an SKF project. When `settings_yml_existed` is true and `patterns_added_list` is not empty, display: "Added {patterns_added} standard exclusions to the reused workspace index settings." When `settings_ready` is false, the command fails or no candidate resolves, set `{ccc_discovery: []}` and continue: this is not an error.

2. **Index the clone:** run `cd "{remote_clone_path}" && ccc index` in the foreground with the shell's longest timeout (in an interactive run, an index that can outlast that timeout may run in the background instead, the step waiting for it to exit before it goes on; a headless run keeps it in the foreground); a call the shell stops at that timeout is a `ccc index` that failed, below. Indexing can take several minutes on large codebases (1000+ files); a reused index processes only what changed. Then load `{cccIndexCheckData}` and run it with `{ccc_root}` = `{remote_clone_path}` and `{ccc_settings_owner}` = `skf`. On **index unverified**, display "CCC index unverified, skipping the language check." and continue to step 3. When `ccc index` fails, or the check returns **degraded**, set `{ccc_discovery: []}` and continue: this is not an error.

3. **Construct semantic query:** build it as `references/ccc-discover.md` §3 says (read that section when it is not in context).

4. **Execute search:** Run `ccc_bridge.search(query, remote_clone_path, top_k=20)` as `cd "{remote_clone_path}" && ccc search --limit 20 "{query}"`. Step 2 has just brought the index up to date, whether it was reused or new, so the search needs no refresh flag.
   - **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or CLI. Note: `ccc search` operates on the index in the current working directory. See `knowledge/tool-resolution.md`.

5. **Store results:** If search succeeds, store as `{ccc_discovery: [{file, score, snippet}]}`. Display: "**CCC semantic discovery: {N} relevant regions identified across {M} unique files.**"

   If step 1 reported `settings_yml_existed` true (an earlier forge's index was reused), append: "(reused workspace index)"

6. **On failure:** Set `{ccc_discovery: []}`. Display: "CCC discovery unavailable, proceeding with standard extraction." Do not halt.

**Leave the workspace clone clean:** run `uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"` from `{project-root}` once this block is done with the clone: after step 5 or step 6, and also when step 1 or step 2 set `{ccc_discovery: []}`, since a `ccc init` or `ccc index`, a failed one too, may have edited the clone's tracked `.gitignore`, which would block a later forge's move of the clone. Resolve `{cccGitHygieneHelper}` from `{cccGitHygieneProbeOrder}` and read nothing from its output; if neither path exists or the command fails, continue: the next resolve repairs the clone before it moves it.

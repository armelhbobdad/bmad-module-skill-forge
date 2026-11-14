<!-- Config: communicate in {communication_language}. -->

# Entry Points by Hand

Where the recipe runner gives no file list or did not diff the entry points, `{extractPublicApiHelper}`'s `--mode denominator` lists the files in scope, counts the public names you find, diffs them with the exports extraction found and decides whether to store `effective_denominator`, by the runner's own rules: no list, count or diff is made by hand. Create-skill's step 3 runs step 1 below at §2 and steps 2 to 4 at §4b; update-skill's write-metadata.md (its write.md §3b) runs them for the same cases. Run each call from `{project-root}`. `<the brief>` and `<the JSON>` are create-skill's `{brief_path}` and `{scope_json}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.scope.json`), and update-skill's `{forge_data_folder}/{skill_name}/skill-brief.yaml` (leave `--brief` out when that file does not exist) and `{run_dir}/denominator.json`.

1. **The files in scope and the entry points**, unless a runner JSON gives them (its `no-ast-grep` result too):

   ```bash
   rm -f "<the JSON>"
   echo '{}' | uv run {extractPublicApiHelper} --mode denominator --source-root "{source_root}" [--brief "<the brief>"] -o "<the JSON>"
   ```

   For a remote source with no local tree, pipe it `gh api "repos/{owner}/{repo}/git/trees/{source_ref}?recursive=1" --jq '.tree[] | select(.type == "blob") | .path'` in place of the `echo`, with `--tree-file -` in place of `--source-root`. The filtered file list is its `files_in_scope_list` (the files a recipe reads) and `files_without_recipes_list` (those in a language no recipe reads): record "**Filtered file count: {`files_in_scope`} files in scope**". The entry points are its `entry_points.files`; a remote source has none: find them with the reads below.
2. **Their public names, each at the file that defines it:**
   - **Python, JavaScript or TypeScript, from a local source:** run `uv run {extractPublicApiHelper} --mode quick --language {language} --source-root "{source_root}" --entry-file <entry-file>`, one `--entry-file` for each entry file of one package, and save its JSON beside `<the JSON>`: each export carries the file that defines it (`defined_in`). Read by eye only the statements its `warnings` name.
   - **Otherwise,** read each entry point: **Python:** `__init__.py`, its imports. **TypeScript/JS:** `index.ts`/`index.js`. **Rust:** `lib.rs`, its `pub use` items. **Go:** the exported (capitalized) identifiers.
   - **A submodule the entry point exports by name** (`from . import sub`, `export * as ns`, a Rust `pub mod`) stands for the names its module passes on: give it its `members`, each at its own file.
3. **The counts and the diff.** Send each name you read by eye in `public` and each export extraction read by eye in `exports`, as `{"name", "file", "language"}` with `file` relative to `{source_root}` and written with `/`:

   ```bash
   uv run {extractPublicApiHelper} --mode denominator --source-root "{source_root}" [--brief "<the brief>"] [--quick "<a quick JSON>"]... [--extraction "<the runner's JSON>"] -o "<the JSON>" <<'SKF_NAMES'
   {"public": [...], "exports": [...]}
   SKF_NAMES
   ```

   Pass each quick JSON of step 2, and `--extraction` when the runner wrote a JSON with status `ok` or `incomplete` (create-skill's `{extraction_json}`, update-skill's `{run_dir}/public-api.json`): its names count too, each once with yours. Leave out `--source-root` for a remote source with no local tree. Its `counts` and `arms` stand in for the runner's. Its `entry_point_diff` replaces a compare by eye: trace each `extraction_gaps` name (re-export protocol), and send each `internal` export with `"internal": true` (create-skill's §5 `add --field exports`), which keeps it out of `metadata.json`'s `exports[]`.
4. **When a call fails:** on exit 2, show the stderr line that holds `error:` and run the call once more, with the payload fixed when that line names it, or with the brief's scope as `--include`, `--exclude`, `--tier-a-include`, `--scope-type` and `--language` in place of `--brief` when it names the brief. When it fails again or writes no JSON, or no `{extractPublicApiHelper}` path resolves, no count is made by hand: the step that loaded this file halts.

**A remote source with no local tree** (step 1 gives no `entry_points.files`): when the in-scope `package.json` declares an `exports` map, read each subpath target, a committed `.d.ts` or `.d.mts` outside `src/` included, as an entry point in step 2. Step 3's diff lists a name defined outside `scope.include` in `outside_scope`: widen `scope.include` to document it.

**If entry point is missing or unreadable:** Skip validation with a warning.

<!-- Config: communicate in {communication_language}. -->

# Entry Points by Hand

Where the recipe runner gives no file list or did not diff the entry points, `{extractPublicApiHelper}`'s `--mode denominator` lists the files in scope, counts the public names you find, diffs them with the exports extraction found and decides whether to store `effective_denominator`, by the runner's own rules: no list, count or diff is made by hand. Create-skill's step 3 runs step 1 below at §2 and steps 2 to 4 at §4b; update-skill's write.md §2 runs them for the same cases. Run each call from `{project-root}`. `<the brief>` and `<the JSON>` are create-skill's `{brief_path}` and `{scope_json}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.scope.json`), and update-skill's `{forge_data_folder}/{skill_name}/skill-brief.yaml` (leave `--brief` out when that file does not exist) and `{run_dir}/denominator.json`.

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

**Multi-entry packages (`exports` map / declaration-file entry points).** A single per-language entry-point read misses public surface that a package ships through its `package.json` `exports` map, especially committed `.d.ts` / `.d.mts` declaration files that resolve **outside** the conventional source dir (e.g. a monorepo package whose `./macro` subpath maps to `macro/index.d.mts`, listed in `files[]` but not under `src/`). When the in-scope package declares an `exports` map:

- Resolve each `exports` subpath to its target file and treat that file, and any committed `.d.ts` / `.d.mts` declaration it resolves to, as an authoritative public entry point, reading it the same way as the primary barrel above even when it lives outside `src/`.
- If a resolved `exports` subpath target falls **outside** the brief's `scope.include` globs, surface a note: `"warn: public entry point {path} (exports subpath '{subpath}') resolves outside scope.include: widen scope.include before extraction, or this surface stays undocumented while exports_public_api still counts it, so public_api_coverage drops (only effective_denominator, for the curated-subset shapes, leaves it out)."` Widening `scope.include` here keeps the documented surface aligned with the `effective_denominator` the runner counts from those same globs, without mid-run scope surgery.

Use the entry point as the authoritative source for `metadata.json`'s `exports[]` array.

**If entry point is missing or unreadable:** Skip validation with a warning.

---
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

<!-- Config: communicate in {communication_language}. -->

# Tier-A Authoring Surface

Loaded by scope-definition.md §3b (step 3) when a monorepo subpackage's `scope.include` uses coarse directory globs (`packages/foo/src/**`, `bin/**`) rather than an explicit file list, and by headless-boundary-defaults.md for its recipe runner alone. Coarse globs also sweep in internal-only files (build scripts, state-store impls, generated config) that the package's public entry barrel never re-exports. `skf-create-skill` scores coverage against the *authoring* surface, and `skf-test-skill` re-derives that surface from the brief to guard against a deflated coverage denominator, so when the coarse-glob union is much larger than the documented export count and the brief names no narrower surface, the test gate inflates the denominator and an otherwise-complete skill scores as if it had large coverage gaps.

Head this off by capturing the authoring surface as **`scope.tier_a_include`**: the concrete source files whose named exports the package's public entry barrel (`index.ts`, `lib.rs`, `__init__.py`) actually re-exports. List the definition files, not the umbrella barrel itself: a barrel re-exports the whole package, so including it widens the surface instead of narrowing it.

- **Forge tier and above: the recipe runner traces the barrel.** It follows every re-export, `export *` and star import from the package's entry points to the file that defines each name. Resolve `{extractPublicApiHelper}` from `{extractPublicApiProbeOrder}` (first existing path wins). It reads the source on disk, at `{source_path}`: a local source, or step 2's `[L]` clone. For a GitHub source step 2 did not clone, the source folder is `{run_dir}/clone`, a clone of only the folders the globs name: step 2 §1's `[L]` clone command with `--sparse` added (and `--filter=blob:none`, which its commit-SHA form already carries), then, right after it (for a commit SHA, before its checkout), `git -C "{run_dir}/clone" sparse-checkout set "<folder>"`, one folder per `scope.include` glob (the part before its first wildcard). From `{project-root}`, run the runner over the confirmed globs, one `--include` per `scope.include` glob and one `--exclude` per `scope.exclude` glob. Once the JSON is written, `--print tier-a-candidates` prints the candidates, one per line:

  ```bash
  uv run {extractPublicApiHelper} --mode full --source-root "<source folder>" --include "<include glob>" --exclude "<exclude glob>" --language "{language}" -o "{run_dir}/tier-a.json" --print tier-a-candidates
  ```

  The candidates are the files that define a name an entry point passes on (`reexport_targets`, the `members` of a namespace in `entry_point_diff.public`, and `entry_point_diff.other_definitions`, each other in-scope file that defines a public name), less the entry points themselves (`entry_points.files[].file`) and the files of the names the runner lists outside the scope (`entry_point_diff.outside_scope`), since a tier A name counts only in a file `scope.include` matches. A file outside `scope.include` that a named re-export (`export { x } from`) or a barrel reaches has no `outside_scope` row and stays a candidate, which Create Skill's runner then warns about.

  Once the runner has run, whatever its exit, remove a clone made for it (`rm -rf "{run_dir}/clone"`).
- **Quick tier, or a runner that cannot trace** (it exits 3 when no ast-grep is installed, 1 or 2 when the scan fails), or a clone that fails (remove what it left, `rm -rf "{run_dir}/clone"`): the candidates are the `reexport_files` step 2 wrote in `{run_dir}/extract.json`, the files its entry files pass names on from. A name passed on from a module step 2 did not fetch stops at that module's file, which may itself re-export, so the list is a first hop there that the confirmation below checks. Log `warn: tier-A surface from step 2's reexport_files ({the reason})`: write it to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. When that list is empty (as it is for any language but Python, JavaScript and TypeScript, the ones whose re-exports step 2 traces), or `{run_dir}/extract.json` holds none (step 2 §4.2 staged no extraction), leave `scope.tier_a_include` unset and say so in the reason, naming the language when it is the cause.

Present the candidate list for the user to confirm or adjust (headless: keep it as it is), and store the confirmed list as `scope.tier_a_include`.

`scope.tier_a_include` does not change what gets extracted (that still follows `scope.include` / `scope.exclude`); it only pins the coverage denominator so the create-side and test-side counts agree without a mid-test hand-edit. Leave it unset when `scope.include` is already an explicit file list, or when the target is not a monorepo subset: there the coarse-glob union and the authoring surface coincide and no narrowing is needed.

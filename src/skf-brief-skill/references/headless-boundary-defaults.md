---
tierASurfaceFile: 'references/tier-a-surface.md'
---

<!-- Config: communicate in {communication_language}. -->

# Headless Boundary Defaults

Loaded by scope-definition.md §3's GATE (step 3) only, when `{headless_mode}` is true and no `include` argument was supplied: each scope type's boundary default, which that GATE takes and records.

| Scope type | Headless default when `include` is absent |
|---|---|
| `full-library` | One module include per module step 2 §4.3 picked, and the default exclusions |
| `public-api` | One include per public API file (below), and the default exclusions |
| `component-library` | The `full-library` default; `scope.registry_path` and `scope.demo_patterns` from scope-definition.md §3's component library detection, each demo pattern also added to the exclusions; every design system variant kept in `scope.ui_variants` |
| `specific-modules` | One module include per module `named_module_subset` names, and the default exclusions. When it names none and the recommender matched `specific-modules-count` (the module count alone), switch to `full-library` and its default, and record the switch in `scope.rationale`: `chosen` `full-library`, `accepted_recommendation` false, `reason` `"headless: specific-modules came from the module count alone and no module was named; full-library boundaries used"`. When it names none and the type came from a `scope_type` argument, halt as below |
| `reference-app` | None: only the caller knows the pattern surface. Halt as below (step 1's input gate already halted a `scope_type=reference-app` argument with no `include`, so this is a type the recommender picked) |

- **A module include** is `<path>/**`, where `<path>` is the module's `path` in `{run_dir}/snapshot.json` (its `workspaces` or `module_candidates` entry, or the entry of `{run_dir}/package-snapshot.json` when §4.3 picked from it): repo-relative, with any workspace prefix already in it. For Maven and Gradle it is the §4.1 `modules` entry, prefixed with `{monorepo_workspace}/` when step 2 picked a workspace. A `named_module_subset` name maps to the §4.3 module it names. With no module picked, the include is `{monorepo_workspace}/**` when step 2 picked a workspace (scope-definition.md §3b), else `**`.
- **The default exclusions** are the Full Library template's test globs (`**/*.test.*`, `**/*.spec.*`, `**/test/**`, `**/tests/**`) and build globs (`**/dist/**`, `**/build/**`, `**/target/**`). The template's configuration and documentation exclusions name no glob, and the module includes already leave the root configuration files and the docs folders out.
- **The public API files** are the files that define the names the package's entry points export. At Forge tier and above, load `{tierASurfaceFile}` for its recipe runner (its helper, source folder, clone and clone removal) and run it with the `full-library` default as its globs, `-o "{run_dir}/public-api.json"` in place of its `-o` and `--print public-files` in place of its `--print`. That prints, one per line, the file of each public name: an entry point's own definitions, the files its re-exports lead to, the files that define a namespace's `members` (the names a submodule the package exports passes on) and each other in-scope file that defines a public name (`entry_point_diff.other_definitions`, such as a name two packages of a monorepo each define). At Quick tier, or when the runner exits 1 to 3, the clone fails or it prints no file, take the `full-library` default instead and give the reason in the warn line scope-definition.md §3's GATE records through `{run_dir}/warning.txt`: `warn: headless boundary default public-api: full-library boundaries ({the reason})`.

A scope with no default emits the halt envelope first, `uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --run-dir "{run_dir}" --target stderr --halt-reason input-missing`, then HALT (exit code 2): "**A headless `{scope_type}` scope needs an `include` argument:** pass the files or folders the skill covers as comma-separated globs, or, for `specific-modules`, name the modules in `intent` or `scope_hint`."

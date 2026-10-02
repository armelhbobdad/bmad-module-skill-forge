# Coverage Check: Tier Branches

Load this file only from coverage-check.md §2, and follow the one section §2 names: **Quick Tier** at Quick tier, **Fallback Per-File Scan** when the Forge-tier recipe runner cannot be used. coverage-check.md's frontmatter bindings, its run files, its per-file results and its §2 **Exits** apply here unchanged. When the section is done, continue in coverage-check.md §2 after the tier that loaded it (at Deep tier, its extra checks; otherwise States 2 to 4 and then §2b).

## Quick Tier

- **A skill quick-skill built** (`metadata.json` `generated_by` is `quick-skill`), **from local source** (State 1): quick-skill built its export list with `{extractPublicApiHelper}` `--mode quick`, so parse the entry points with the same parser and both sides count one surface. Resolve it ← first existing path in `{extractPublicApiProbeOrder}` and run it once per package in scope, with its manifest and one `--entry-file` for each entry-point file the Source API Surface Definition makes its surface, each path relative to `{source_path}` (`<n>` counts the packages from 1):

  ```bash
  uv run {extractPublicApiHelper} --mode quick --language <language> --source-root "{source_path}" --manifest-file <manifest path> --entry-file <entry path> > "{run_dir}/quick-<n>.json"
  ```

  Its `warnings` name each statement whose names the entry file alone cannot give. Read by eye only the statements its warnings name, save the names they give as a per-file result for the entry file that holds the statement, `{"file": "<entry path>", "exports_found": [<each name>], "signature_mismatches": []}`, and list those names in the Coverage Analysis section as read by eye. Give `surface` one `--quick` per package, one `--per-file` per saved result, the brief when the skill has one (its globs give the `scope.include` and `tier_a_include` sets), the metadata and, when init.md §2 bound one, the provenance map (the baselines of the §2b candidates and guards; they add no name):

  ```bash
  uv run {coverageInputsScript} surface --quick "{run_dir}/quick-<n>.json" [--per-file "{run_dir}/per-file-<n>.json"] [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/surface.json"
  ```

- **Any other skill** (create-skill's Quick tier reads the entry points as source text), a source that is not local, or a helper that does not resolve or exits non-zero (it exits 1 on a language it does not parse): identify the exports by reading the entry points per the Source API Surface Definition, save one per-file result per entry file, run the `surface` command above with no `--quick`, and note in the Coverage Analysis section that the Quick-tier scan read them by eye.

## Fallback Per-File Scan

The recipe runner cannot be used, so subagents read the files in scope one at a time. List every documented signature first: `plan` without `--surface` writes the map as `documentedSignatures`:

```bash
uv run {scoreSignaturesScript} plan --inventory "{run_dir}/inventory.json" --output "{run_dir}/signature-plan.json"
```

For each source file that defines public API exports, delegate a subagent that gets that map with the file. It extracts the file's exported symbols with their full signatures with ast-grep (or reads the file when `extraction.fallback.reason` says no ast-grep can run; list those files in the Coverage Analysis section as read by eye), compares each with the map's entry (params, return type), gives each mismatch the `line` that defines the export, and returns only `{"file", "exports_found": [...], "types_found": [<the exported interfaces, type aliases, enums and classes>], "signature_mismatches": [...]}`, each mismatch in the shape §2's signature comparison returns. Save each response to `{run_dir}/per-file-<n>.txt` with the Write tool and build the surface from them, one `--per-file` each, with the same baselines as at Quick tier:

```bash
uv run {coverageInputsScript} surface --per-file "{run_dir}/per-file-<n>.txt" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/surface.json"
```

coverage-check.md §2b scores these responses once it has picked the denominator set.

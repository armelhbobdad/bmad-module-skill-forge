# CCC Index Check

Step 3 §2a (deferred ccc discovery on SKF's workspace clone) and step 7 §6b (the index the skill registers) load this file after they run `ccc index`. It checks, through `{mergeCccExclusionsHelper}`, that the source language was indexed, and repairs the index settings when it was not. The caller binds:

- `{ccc_root}`: the folder the index belongs to. ccc takes no path argument, so every ccc command below runs as `cd "{ccc_root}" && ccc ...`.
- `{ccc_settings_owner}`: `skf` when `{ccc_root}` is SKF's workspace clone of a remote source, whose `settings.yml` SKF edits only through `{mergeCccExclusionsHelper}`; `user` when `{ccc_root}` is the user's own source folder, whose `settings.yml` SKF never edits.

`{mergeCccExclusionsHelper}` is the first existing path in the caller's `mergeCccExclusionsProbeOrder`; run it from `{project-root}`.

## 1. Check the Index

Take the extensions of the `{brief.language}` files in step 3's §2 filtered file list, at most 3, and run, with one `--include-ext` per extension:

```bash
uv run {mergeCccExclusionsHelper} --check-index "{ccc_root}" --language "{brief.language}" --include-ext {ext}
```

It reads `ccc status` in `{ccc_root}` and, while a pass is still running, runs `ccc index` again (which waits for that pass, then makes a quick incremental one), up to 3 times, so run the call in the foreground with the shell's longest timeout: a call the shell stops prints no JSON. It runs no `ccc init` and never edits `settings.yml`. The language is indexed when ccc counts at least 10 chunks of it, or above 0 and at least 5% of all chunks in a smaller index (its `threshold`): an index of markdown and config chunks with the source language absent or near zero means the source code was never indexed, and searches over it return nothing useful. Branch on its `verdict`:

- **`verified`:** return **verified**.
- **`unverified`** (a pass still runs after the reruns, or a ccc command failed; `reason` says which), and also when no path resolves or the call prints no JSON: return **index unverified** to the caller and skip §2.
- **`degraded`:** repair the settings in §2.

## 2. Repair

Apply these repairs in order. After a repair that changes the settings, run a plain `cd "{ccc_root}" && ccc index` in the foreground with the shell's longest timeout, then §1's call again; stop at the first one after which its `verdict` is `verified`, and return **verified**.

1. **No project of its own:** `project.settings_yml` and `project.is_root` are both false: `{ccc_root}` has no `.cocoindex_code/settings.yml` and ccc indexed the enclosing project its `project.path` names. With `{ccc_settings_owner}` `skf`, run `uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}"`: it runs `ccc init -f` there and adds the standard build and dependency exclusions. With `user`, run `cd "{ccc_root}" && ccc init -f`.
2. **Language not included:** ccc indexes only the file types listed in `include_patterns`, and its default list leaves some languages out (Elixir's `.ex`, for example). Use the extensions §1 took.
   - `skf`: run `uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}" --include-ext {ext}`, with one `--include-ext` per extension. It appends a single-quoted `- '**/*.{ext}'` item for each extension no `include_patterns` entry matches (`includes_added_list`) and lists the extensions an entry already matches (`includes_covered_list`). On a file with no `include_patterns` list it adds nothing and says so in `warnings`, since a list written from scratch replaces ccc's default file types: display that `{ccc_root}/.cocoindex_code/settings.yml` has no `include_patterns` list to add the `{brief.language}` file types to, and return **degraded**. When `includes_covered_list` holds every extension, the files are excluded rather than left out of `include_patterns`: skip this repair and display which `exclude_patterns` entry covers the `{brief.language}` source files (`**/build` covers a package under `src/build/`, for example). Otherwise display "Added {includes_added_list} to include_patterns in {ccc_root}/.cocoindex_code/settings.yml so ccc indexes {brief.language} files.", then run `ccc index` and §1's call again.
   - `user`: the settings belong to the user's project, so do not edit them. Read §1's last `unmatched_exts`, the extensions no `include_patterns` entry matches. When it is null, display that `{ccc_root}/.cocoindex_code/settings.yml` has no `include_patterns` list to add the `{brief.language}` file types to. If it is empty, the files are excluded rather than left out of `include_patterns`: display which `exclude_patterns` entry covers the `{brief.language}` source files. Otherwise display that ccc did not index `{brief.language}` files, and the exact lines to add under `include_patterns` in `{ccc_root}/.cocoindex_code/settings.yml`, one single-quoted `- '**/*.{ext}'` line per extension of `unmatched_exts` (YAML reads an unquoted leading `*` as an alias, and ccc then fails to load the file), followed by a plain `ccc index`.

A plain `ccc index` is enough after any `settings.yml` edit; nothing needs deleting first. Do not run `ccc reset`: it deletes only the index databases and keeps `settings.yml`, so it cannot repair the settings, a `ccc index` right after it can fail and leave the project with no index, and run from a folder without its own `settings.yml` it deletes the enclosing project's index. If the `verdict` is still not `verified` after these repairs, return **degraded** to the caller.

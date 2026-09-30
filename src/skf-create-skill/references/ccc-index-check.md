# CCC Index Check

Step 3 §2b (deferred ccc discovery on SKF's workspace clone) and step 7 §6b (the index the skill registers) load this file after they run `ccc index`. It waits for a running pass, checks that the source language was indexed, and repairs the index settings when it was not. The caller binds:

- `{ccc_root}`: the folder the index belongs to. ccc takes no path argument, so every ccc command below runs as `cd "{ccc_root}" && ccc ...`.
- `{ccc_settings_owner}`: `skf` when `{ccc_root}` is SKF's workspace clone of a remote source, whose `settings.yml` SKF edits only through `{mergeCccExclusionsHelper}`; `user` when `{ccc_root}` is the user's own source folder, whose `settings.yml` SKF never edits.

`{mergeCccExclusionsHelper}` is the first existing path in the caller's `mergeCccExclusionsProbeOrder`; run it from `{project-root}`.

## 1. Wait for the Pass

Run `cd "{ccc_root}" && ccc status`. If it prints an `Indexing in progress:` line, a pass is still running and the counts below it are not final: run `cd "{ccc_root}" && ccc index` again, which waits for the running pass to finish and then makes a quick incremental pass, then run `ccc status` again. If the line is still there after 3 such runs, return **index unverified** to the caller and skip §2 and §3.

## 2. Check the Languages

Once the line is gone, read the `Languages:` breakdown: a non-zero `Chunks`/`Files` total is not sufficient. Confirm the source's primary language (`{brief.language}`) reports a non-trivial chunk count. An index dominated by `markdown`/config chunks with the source language absent or near-zero means the source code was never indexed, and searches over it return nothing useful. When the source language is there, return **verified**.

## 3. Repair

When the source language is absent, apply these repairs in order, stopping at the first one after which `Languages:` shows the source language:

1. **No project of its own:** `{ccc_root}/.cocoindex_code/settings.yml` is missing and the `Project:` line of `ccc status` names another folder, so ccc indexed an enclosing project. With `{ccc_settings_owner}` `skf`, run `uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}"`: it runs `ccc init -f` there and adds the standard build and dependency exclusions. With `user`, run `cd "{ccc_root}" && ccc init -f`. Then run `ccc index`, then run `ccc status` and check `Languages:` again.
2. **Language not included:** ccc indexes only the file types listed in `include_patterns`, and its default list leaves some languages out (Elixir's `.ex`, for example). Take the extensions of the `{brief.language}` files in step 3's §2 filtered file list, at most 3.
   - `skf`: run `uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}" --include-ext {ext}`, with one `--include-ext` per extension. It appends a single-quoted `- '**/*.{ext}'` item for each extension no `include_patterns` entry matches (`includes_added_list`) and lists the extensions an entry already matches (`includes_covered_list`). On a file with no `include_patterns` list it adds nothing and says so in `warnings`, since a list written from scratch replaces ccc's default file types: display that `{ccc_root}/.cocoindex_code/settings.yml` has no `include_patterns` list to add the `{brief.language}` file types to, and return **degraded**. When `includes_covered_list` holds every extension, the files are excluded rather than left out of `include_patterns`: skip this repair and display which `exclude_patterns` entry covers the `{brief.language}` source files (`**/build` covers a package under `src/build/`, for example). Otherwise display "Added {includes_added_list} to include_patterns in {ccc_root}/.cocoindex_code/settings.yml so ccc indexes {brief.language} files.", run a plain `cd "{ccc_root}" && ccc index`, then run `ccc status` and check `Languages:` again.
   - `user`: the settings belong to the user's project, so do not edit them. Keep the extensions that no `include_patterns` entry matches. If there are none, the files are excluded rather than left out of `include_patterns`: display which `exclude_patterns` entry covers the `{brief.language}` source files. Otherwise display that ccc did not index `{brief.language}` files, and the exact lines to add under `include_patterns` in `{ccc_root}/.cocoindex_code/settings.yml`, one single-quoted `- '**/*.{ext}'` line per extension (YAML reads an unquoted leading `*` as an alias, and ccc then fails to load the file), followed by a plain `ccc index`.

A plain `ccc index` is enough after any `settings.yml` edit; nothing needs deleting first. Do not run `ccc reset`: it deletes only the index databases and keeps `settings.yml`, so it cannot repair the settings, a `ccc index` right after it can fail and leave the project with no index, and run from a folder without its own `settings.yml` it deletes the enclosing project's index. If the source language is still missing after these repairs, return **degraded** to the caller.

---
created: "2026-04-08 00:11"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: observations
source_ids: [4588, 4597, 4622]
---

# Uninstall scans every platform instead of trusting the manifest

`skf uninstall` cleans IDE skills with `removeAllSkfSkills(projectDir, { moduleDir, manifest })` in `tools/cli/lib/ide-skills.js`, which walks the `target_dir` of every platform in `platform-codes.yaml` (and its `legacy_targets`) and removes `skf-*` entries whole; it never keys on `manifest.ides` or `manifest.directories`. Since PR #1280 (issue #1279), inside an IDE `shared/` or `knowledge/` it removes only SKF's files: a regular file whose bytes equal its copy in `_bmad/skf/` on disk or in the running package's `src/`, or one `files.ide_skills` lists, plus the `__pycache__`, `.pyc` and OS files beside such a match; it never follows a link, and it keeps everything else and names it in a warning. Install and update run the same classifier on each selected IDE before writing anything and stop with exit 1 (`IdeFolderInUseError`) when a `shared/` holds a file SKF did not install; `knowledge/` is no longer copied into IDE folders, and `writeManifest` lists nothing under an IDE `knowledge/`. Scanning every platform is deliberate: when `manifest.js` renamed `files.ide_commands` to `files.ide_skills` (2026-04-07), uninstall kept reading `ide_commands` and silently left every `.{ide}/skills/` folder on disk, and pre-migration command files were never in the manifest at all. So never let a manifest field decide which folders uninstall scans (the manifest may only mark files found inside the two support folders), and change the manifest writer (`manifest.js`) in the same commit as its readers (`uninstall.js`, `ide-skills.js`).

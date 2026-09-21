---
created: "2026-04-08 00:11"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: observations
source_ids: [4588, 4597, 4622]
---

# Uninstall scans every platform instead of trusting the manifest

`tools/cli/commands/uninstall.js` removes IDE skills with `removeAllSkfSkills(projectDir)` from `tools/cli/lib/ide-skills.js`, which walks every platform in `platform-codes.yaml` and deletes `skf-*`, `knowledge/` and `shared/` under each `target_dir` plus its `legacy_targets`, ignoring what `_bmad/_config/skf-manifest.yaml` lists under `files.ide_skills`; the manifest only drives the count and the removal-plan display, `_skf-learn` and output scaffolding. This is deliberate: when `manifest.js` renamed `files.ide_commands` to `files.ide_skills` (2026-04-07), uninstall kept reading `ide_commands` and silently left every `.{ide}/skills/` directory on disk with no error, and pre-migration command files were never in the manifest at all. The header comment "Uses the manifest to know exactly what to remove" is stale for the IDE part — do not make uninstall "precise" by trusting the manifest, and change the manifest writer (`manifest.js`) and its reader (`uninstall.js`) in the same commit.

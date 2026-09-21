---
created: "2026-04-08 10:20"
session: "02f8c828-1c77-4b73-a8f1-4a12a461890e"
source: claude-mem
source_table: both
source_ids: [4702, 4704, 4721, 4722, 4723]
---

# module.yaml and module-help.csv stay at src/ root

`src/module.yaml` and `src/module-help.csv` live at the `src/` root: `tools/cli/lib/installer.js` copies them from `this.srcDir` behind an `fs.pathExists` check, so if they are moved the installer silently skips them and installed projects lose their module metadata (`test/test-installation-components.js` also reads `src/module.yaml`). On 2026-04-08 they were moved into `src/skf-setup/assets/` to satisfy bmad-module-builder's `validate-module.py` (commit f670a117, validator passed) and reverted the same day with `git mv` (commit d698194a, restoring the layout shared with bmad-module-creative-intelligence-suite). The validator's `Missing required file: assets/module.yaml` finding is a known, accepted convention (see the bmb-validate-module-skf-layout note): do not relocate the files to silence it. `src/README.md` documents the root location and still tells contributors to run `bmad:bmb:modules:validate-module` for module-level edits.

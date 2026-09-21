---
created: "2026-04-05 14:09"
session: "53d6f9f3-91c9-4d9b-8940-f076ae12b1e2"
source: claude-mem
source_table: session_summaries
source_ids: [1721, 1805, 1807, 1301, 1302, 1303, 1362, 1366, 1367, 14650, 14657]
---

# BMB validate-module fails against the SKF src/ layout by design

Running the BMad Builder validator against this module — `python3 .claude/skills/bmad-module-builder/scripts/validate-module.py src` — returns `"status": "fail"` with two critical findings, `Missing required file: assets/module.yaml` and `Missing required file: assets/module-help.csv`. That is expected, not a defect: SKF deliberately keeps `module.yaml` and `module-help.csv` at `src/` root (`tools/cli/lib/installer.js` copies them from the src root, and CHANGELOG records "restore module.yaml and module-help.csv to src/ root" after a short-lived move into `src/skf-setup/assets/`), `skf-setup` is an operational skill (tool detection, tier selection) rather than a BMB-style module installer, and SKF ships its own installer at `tools/cli/skf-cli.js`. The ship gate is the native suite in `npm run quality` (`validate:skills`, `validate:refs`, `validate:docs-links`, `docs:validate-drift`), so do not restructure `src/` to satisfy validate-module. `src/README.md` still tells contributors to validate module-level edits with `bmad:bmb:modules:validate-module`; expect it to fail this way.

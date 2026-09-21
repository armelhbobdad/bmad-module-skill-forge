---
created: "2026-03-08 18:52"
session: "883a7c2c-6ff9-4c83-aa11-e66236b0ad67"
source: claude-mem
source_table: session_summaries
source_ids: [304, 305, 306, 240, 274, 275]
---

# npx resolves the package name, not bin aliases

`package.json` declares a single bin, `bmad-module-skill-forge` -> `tools/skf-npx-wrapper.js`. A second alias (`skill-forge`, removed in commit 46c57301) never made `npx skill-forge install` work: with no prior install, `npx <name>` resolves `<name>` as an npm *package* name, not a bin name, so an alias either 404s on the registry (`npm view skill-forge` -> E404) or fetches whatever unrelated package owns that name (`skill-check` is the external linter skf-test-skill calls, `skf` is an unrelated 0.0.3 package). Only `npx bmad-module-skill-forge <command>` works standalone, so docs and CLI messages (tools/cli/commands/*.js, tools/cli/lib/version-check.js) must keep the full package name. Bin aliases only help once the package is installed locally, which is why workflows inside an installed project can use the local bin.

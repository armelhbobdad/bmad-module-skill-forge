---
created: "2026-03-29 15:25"
session: "e7f152a5-05f4-4fb1-80d8-260dfaef98d3"
source: claude-mem
source_table: observations
source_ids: [3267, 3268]
---

# No trailing slash on path config defaults

Path config variables in `src/module.yaml` (`skills_output_folder`, `forge_data_folder`, `sidecar_path` — default `_bmad/_memory/forger-sidecar`) and the installer default in `tools/cli/lib/installer.js:262` carry no trailing slash. Workflow references build paths by concatenation — `{sidecar_path}/forge-tier.yaml`, `{sidecar_path}/preferences.yaml` (57 `{sidecar_path}/` sites under `src/`) — so a value ending in `/` yields double-slash paths such as `_bmad/_memory/forger-sidecar//forge-tier.yaml`. This was hit once in the former `forger.agent.yaml` `sidecar-path` metadata (`{project-root}/_bmad/_memory/forger-sidecar/`) and fixed by stripping the slash. When adding a new path variable or default anywhere, keep the value slash-free and let the consumer add the separator; nothing in the repo lints for this.

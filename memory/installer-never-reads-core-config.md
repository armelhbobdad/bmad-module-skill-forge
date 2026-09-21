---
created: "2026-05-23 23:48"
session: "0f8aff23-aa36-4277-9437-7f462519232e"
source: claude-mem
source_table: observations
source_ids: [11514, 11516, 11521, 11525]
---

# Installer never reads BMAD Core Config

`src/module.yaml` lists `user_name`, `communication_language`, `document_output_language` and `output_folder` under "Variables from Core Config inserted", and `docs/getting-started.md:183` calls `output_folder` "Inherited from BMAD Core Config", but `tools/cli/lib/installer.js` never reads any Core Config: `writeConfig` serialises a fixed `configData` object into `_bmad/skf/config.yaml` and nothing else. Until PR #376 (commit 77f18c3) that object had no `output_folder`, so on a clean install `skf-refine-architecture` and `skf-create-stack-skill` halted with "Cannot proceed. `output_folder` is not configured in config.yaml" (exit 3, `halt_reason: "output-folder-unconfigured"`), and the same class had already hit `skf-test-skill` earlier (#50, "undefined {output_folder}"). Any variable a workflow reads from `config.yaml` that module.yaml calls Core-Config-inserted must be written explicitly in `configData` (installer.js ~line 259, `output_folder: config.output_folder || '_bmad-output'`) and asserted in `test/test-cli-integration.js` (line 117 does this for `output_folder`); "inherited" in the docs is not something the installer implements.

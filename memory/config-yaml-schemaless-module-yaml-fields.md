---
created: "2026-04-12 00:19"
session: "72420630-d63c-47ad-a7f5-8ac1c35bb3c6"
source: claude-mem
source_table: observations
source_ids: [5745, 5746]
---

# config.yaml is schema-less; module.yaml lists only installer-prompted fields

`_bmad/skf/config.yaml` is written by `writeConfig()` in `tools/cli/lib/installer.js` from a hand-written key set (`src/module.yaml` is read only for the `health_check_repo` default) and read back as free-form YAML: `skf-setup` halts only on a missing file (`on-activation:config-missing`) or a YAML parse error (`on-activation:config-malformed`), and there is no schema, validator or installer template to update when a workflow gains a config key. `src/module.yaml` declares only the four installer-owned fields (`skills_output_folder`, `forge_data_folder`, `sidecar_path`, `health_check_repo`). Opt-in runtime keys such as `snippet_skill_root_override` are deliberately kept out of it: they have no default, the workflows test "is set in config.yaml", and consuming projects must not get them written at install time. To add an optional key, document it in the owning skill (as skf-export-skill does in `SKILL.md` and `assets/managed-section-format.md`) and let the user add it to config.yaml by hand; do not add it to module.yaml.

---
created: "2026-04-03 18:41"
session: "1515905c-e1d7-40f7-8c23-5f52e1cd284a"
source: claude-mem
source_table: observations
source_ids: [4057, 4065, 4066, 4067, 4068]
---

# Installer writeConfig() hardcodes config.yaml keys

`tools/cli/lib/installer.js` `writeConfig()` builds the installed `config.yaml` from a hand-written object (`user_name`, `project_name`, `output_folder`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`, `skf_folder`, `health_check_repo`, `ides`, `install_learning`) and reads `src/module.yaml` only for the `health_check_repo` default; on update it restores the saved YAML verbatim and injects only `health_check_repo`. A variable added to `src/module.yaml` — especially a `prompt: false` one — therefore never reaches an installed `config.yaml` until both branches of `writeConfig()` are edited by hand, and `test/test-installation-components.js` only asserts `health_check_repo`. When `sidecar_path` was missing, every step reading `{sidecar_path}/forge-tier.yaml` found nothing and silently compiled at Quick tier with plausible-looking output; blaming the upstream BMAD Core installer's handling of `prompt: false` was never verified and the user redirected: "is it not possible to fix it in skf standalone installer?" The fix was adding `sidecar_path: '_bmad/_memory/forger-sidecar'` to `writeConfig()`; `src/skf-forger/SKILL.md` On Activation now HARD HALTs when `{sidecar_path}` does not resolve, so a missing key surfaces instead of degrading.

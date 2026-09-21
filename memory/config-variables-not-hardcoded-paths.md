---
created: "2026-03-26 09:55"
session: "3dd3e331-e889-4e24-bd99-554a5ca4d2fa"
source: claude-mem
source_table: observations
source_ids: [2527, 2570, 2581]
---

# Config variables instead of hardcoded folder paths in step files

`skills_output_folder` and `forge_data_folder` are installer prompts (`src/module.yaml`, `tools/cli/lib/ui.js:207-219`) persisted to `skf-manifest.yaml`, so SKILL.md and `references/*.md` step files must reference `{skills_output_folder}`, `{forge_data_folder}` (and `{sidecar_path}`, `{output_folder}`) rather than literal `skills/` or `forge-data/` — a hardcoded default silently breaks any install that changed the prompt, and a skill's activation must resolve these variables or downstream steps hit undefined references. Nothing enforces this: `tools/validate-file-refs.js` only whitelists the variable names (lines 123-125) and flags absolute-path leaks (`/home/`, `/Users/`), so a literal `forge-data/...` path passes `npm run quality` and is caught only in review (a March 2026 pre-push review found such paths in create-skill, setup-forge and verify-stack steps). `sidecar_path` is `prompt: false` with the fixed default `_bmad/_memory/forger-sidecar`; `skf-setup` writes it as a literal path while every other skill uses `{sidecar_path}`.

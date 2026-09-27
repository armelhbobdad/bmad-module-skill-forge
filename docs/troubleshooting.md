---
title: Troubleshooting
description: Common errors in Skill Forge — forge setup, ecosystem checks, tier confidence — and how to resolve them.
---

If something isn't working, start here. For general setup help see [Getting Started → Need help?](/docs/getting-started.md#need-help).

---

## Common errors

### "Setup cannot proceed: `uv` is not installed"

Surfaced by `/skf-setup` On Activation when `uv --version` is missing on `$PATH`. SKF helpers depend on `uv` to auto-resolve their Python dependencies via PEP 723 inline metadata; bare `python3` ignores that metadata and would fail later with `ModuleNotFoundError: No module named 'yaml'`. The probe halts the workflow up-front with one cohesive diagnostic instead of letting five steps each fail individually. Under `--headless` or `--quiet`, the same text arrives as the `error.reason` of a `status: "blocked"` `SKF_SETUP_RESULT_JSON` envelope.

**Fix:** install `uv` from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`. `uv` is documented as a runtime prerequisite in [Getting Started → Prerequisites](/docs/getting-started.md#prerequisites-full-reference).

### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"

Surfaced by `/skf-setup` On Activation when the SKF install config is missing — typically because you invoked `/skf-setup` from a directory that is not an SKF-initialised project. The check runs before any file mutation so nothing is written. Under `--headless` or `--quiet`, the same text arrives as the `error.reason` of a `status: "blocked"` `SKF_SETUP_RESULT_JSON` envelope only when SKF's scripts are installed in the project. In the typical case they are not (a directory that is not an SKF project, or an install whose scripts are gone), so there is no helper to build an envelope: the run's one line is this reason alone. Pipelines should treat a missing envelope as a failure.

**Fix:** from the project root, run `npx bmad-module-skill-forge install` (or `npx bmad-method install` and add SKF as a custom module — see [Getting Started → Install](/docs/getting-started.md#install)), then re-run `/skf-setup`. If you ARE in the right project but the file was deleted, restore it from version control or re-run the SKF installer. A separate "config.yaml is not valid YAML" diagnostic surfaces the parser error inline if the file exists but is malformed — open the file at the named path and repair the YAML.

### Forge reports ast-grep is unavailable

If setup reports that ast-grep was not detected, install it to unlock the Forge tier: <https://ast-grep.github.io>. Re-run `@Ferris SF` afterward — your tier upgrades automatically.

### "No skill brief found"

Run `@Ferris BS` first to create a skill brief, or use `@Ferris QS` for brief-less generation. `CS` always requires a brief — either a `skill-brief.yaml` produced by `BS` (or `AN`), or pass the skill name so it resolves one from your forge-data folder. For brief-less generation use `QS`.

### "Ecosystem check: official skill exists"

An official skill already exists for this package. Consider installing it with `npx skills add` instead of generating your own — the official skill is typically better tested and kept up-to-date by the library maintainer.

### Quick-tier skills have lower confidence scores

Quick tier reads source without AST analysis, so signatures are read directly from files rather than structurally verified. Install ast-grep to upgrade to the Forge tier for AST-verified signatures (T1 confidence) — see [Capability Tiers](/docs/concepts.md#capability-tiers-quickforgeforgedeep).

### Want semantic discovery for large codebases?

Install [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) to unlock the Forge+ tier. CCC indexes your codebase and pre-ranks files by semantic relevance before AST extraction, improving coverage on projects with 500+ files.

### `@Ferris deepwiki` shows a deprecation notice

The auto pipeline was briefly named `deepwiki`; it's now [`forge-auto`](/docs/forge-auto.md) — renamed to avoid confusion with the DeepWiki MCP, since the pipeline compiles a verified skill from source and does **not** call that MCP. `deepwiki` still works (it resolves to `forge-auto`) but prints a one-time notice. Switch your commands to `@Ferris forge-auto <repo-or-doc-url>`.

### `@Ferris onboard` returns an error

The `onboard` alias was removed. Its replacement is [`forge-auto`](/docs/forge-auto.md), which does everything `onboard` did plus auto-scope, auto-brief, and a stricter 90% quality gate. Run `@Ferris forge-auto <repo-or-doc-url>` instead.

### forge-auto halted at the Test stage

forge-auto runs Test Skill with a stricter **90% quality threshold** (vs the default 80%), so a skill that scores below 90% halts at TS with a gap report rather than exporting a weak skill. Run `@Ferris US` to address the gaps it lists, then `@Ferris TS EX` to re-test and export. If 90% is stricter than you need, run the individual workflows or `forge` instead, which use the default threshold.

### "`<name>` is not SKF output"

Surfaced when create-skill, quick-skill or create-stack-skill would write a new version into a skill folder that already exists, when update-skill, export-skill, audit-skill or test-skill would move a flat skill into the versioned layout, or when drop-skill would delete or rename-skill would rename a skill, and that folder in `skills_output_folder` is one SKF did not generate, such as a BMad module's own skills or skills installed from another tool. SKF only writes into, migrates, renames or purges a skill whose `metadata.json` carries the SKF marker, so the workflow stops before it changes anything. Drop and rename also refuse a skill folder that mixes SKF output with other files, and rename and the three writers refuse a skill that is still in the old flat layout (`flat-layout`). Drop and rename check the skill's folder in `forge_data_folder` too: they refuse one that mixes SKF's brief and reports with other files (rename also refuses one that is a link, is not a folder, or cannot be listed), and leave a folder there SKF did not generate, such as another tool's folder of the same name, where it is; drop names it as "Left in place (not SKF output)".

**Fix:** a `skills_output_folder` shared with skills from elsewhere is supported, and SKF leaves the skills it did not generate alone, so manage `<name>` yourself (to remove it, delete its folder). For create-skill, set a different `name` in the brief to create the skill beside that folder; for create-stack-skill, choose a different `project_name`; Quick Skill names a skill after its target, so use Brief Skill and Create Skill to pick another name. If the entries SKF names are in `forge_data_folder/<name>/`, move your own files out of that folder (for a link, replace it with the folder it points to; for a path that is not a folder or cannot be listed, move it out of the way or fix its permissions), then re-run. Relocate only when the folder holds a module's own source rather than skills: then set `skills_output_folder` in `_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there, and re-run `/skf-setup`. If SKF did generate the skill and its `metadata.json` was edited or lost, restore that file; if the message says SKF cannot read it (for example `Unexpected UTF-8 BOM`), re-save it as plain UTF-8. For `flat-layout`, run `@Ferris TS <name>` once to move the skill into the versioned layout, then re-run the workflow that stopped. If the entries SKF names include a version folder with no `metadata.json`, an interrupted update-skill, create-skill, quick-skill or create-stack-skill run may have left it: delete that folder, then re-run the workflow. An entry named `<version>/<entry>` is a file or folder placed inside an SKF version folder: move it out of `<name>/<version>/`, then re-run.

**`<name>` still uses the flat layout:** update-skill `--detect-only` and `--dry-run` never move a skill, but they need the versioned layout, so they stop on an SKF skill that is still flat. Run `@Ferris US <name>` once without the flag (or AS, TS or EX) to move it into the versioned layout, then re-run with the flag.

**Skills an earlier SKF already moved:** an SKF release without this check could move a module's flat skill into `<name>/<version>/<name>/` and add an `active` link. Recover it from version control: `git status` shows what moved, `git restore <skills-folder>/<name>` brings back the original files, and you then delete the `<version>/` folder and `active` link that SKF added. The same recovery applies when an SKF release without this check wrote a new version into such a folder: delete the `<version>/` folder and `active` link it added, and restore any file it replaced with `git restore`. Until then, `/skf-setup` keeps those skills in the ccc index while no marked SKF version sits in them, since they carry no SKF marker, and warns when the folder holds no SKF output at all.

**`skills_output_folder` or `forge_data_folder` set to `_bmad-output`:** create-skill stages a skill in `_bmad-output/.skf-stage/<name>/` before it writes the version. An earlier SKF release staged it in `_bmad-output/<name>/`, which with this setting is also the skill's folder or its forge folder, and left `SKILL.md`, `metadata.json`, `context-snippet.md`, `references/`, `evidence-report.md` and `provenance-map.json` at the root of that folder. That leftover can make create-skill stop with `flat-layout`, and make drop and rename refuse the skill folder or its forge folder as one that holds entries SKF did not generate. Delete those leftovers yourself and keep everything else in the folder, such as the `<version>/` folders, the `active` link and `skill-brief.yaml`; when the folder holds nothing but the leftovers, delete it whole. Then re-run.

### My campaign stopped partway — how do I resume?

Campaign is designed for exactly this. State lives in `_campaign-state.yaml` on disk, so context death, a session timeout, or a machine restart loses nothing. Run `@Ferris campaign resume` — Ferris validates the state file, skips completed skills, and picks up from the next incomplete skill in dependency order. If the state file is corrupted, Ferris falls back to the `.bak` copy automatically. To re-process one specific skill, use `@Ferris campaign resume --from=<skill>`.

---

## Still stuck?

1. Run `@Ferris SF` to check your tool availability and current tier
2. Check `forge-tier.yaml` in your forger sidecar for your configuration
3. If `/bmad-help` is installed (via full BMAD Method), run it and describe your state — e.g. `/bmad-help my batch creation failed halfway, how do I resume?`
4. [File an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — SKF's [health check system](/docs/workflows.md#terminal-step-health-check) is the primary feedback channel, and manual issues feed the same pipeline

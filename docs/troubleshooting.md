---
title: Troubleshooting
description: Common errors in Skill Forge — forge setup, ecosystem checks, tier confidence — and how to resolve them.
---

If something isn't working, start here. For general setup help see [Getting Started → Need help?](/docs/getting-started.md#need-help).

---

## Common errors

### "Setup cannot proceed: `uv` is not installed"

Surfaced by `/skf-setup` On Activation when `uv --version` is missing on `$PATH`. SKF helpers depend on `uv` to auto-resolve their Python dependencies via PEP 723 inline metadata; bare `python3` ignores that metadata and would fail later with `ModuleNotFoundError: No module named 'yaml'`. The probe halts the workflow up-front with one cohesive diagnostic instead of letting five steps each fail individually. Under `--headless` or `--quiet`, the same text arrives as the `error.reason` of a `status: "blocked"` `SKF_SETUP_RESULT_JSON` envelope. The envelope helper needs only the Python standard library, so setup builds that envelope with the first of `python3`, `python` or `py -3` that runs on the machine. With none of them, the run's one line is this reason alone. Pipelines should treat a missing envelope as a failure.

**Fix:** install `uv` from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`. `uv` is documented as a runtime prerequisite in [Getting Started → Prerequisites](/docs/getting-started.md#prerequisites-full-reference).

### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"

Surfaced by `/skf-setup` On Activation when the SKF install config is missing — typically because you invoked `/skf-setup` from a directory that is not an SKF-initialised project. The check runs before any file mutation so nothing is written. Under `--headless` or `--quiet`, the same text arrives as the `error.reason` of a `status: "blocked"` `SKF_SETUP_RESULT_JSON` envelope only when SKF's scripts are installed in the project and `uv` or a Python interpreter can run them. In the typical case they are not (a directory that is not an SKF project, or an install whose scripts are gone), so there is no helper to build an envelope: the run's one line is this reason alone. Pipelines should treat a missing envelope as a failure.

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

### `git status` lists a `.cocoindex_code` folder inside a source folder

When ccc is available (Forge+, or Deep with ccc), create-skill indexes the skill's source with it. A local source folder inside your project or inside another git checkout (a subfolder such as `./packages/lib`, a linked worktree or a submodule) becomes a ccc project of its own, and ccc does not gitignore an index there. create-skill keeps it out of git by writing a `.gitignore` holding `*` inside that `.cocoindex_code/` folder, and says so in one line; it never edits your own `.gitignore`. For a folder an earlier SKF release left untracked, run create-skill for that source again, or create `<source>/.cocoindex_code/.gitignore` holding the single line `*`. If you already committed the index, `git rm -r --cached <source>/.cocoindex_code` stops tracking it.

### `@Ferris deepwiki` shows a deprecation notice

The auto pipeline was briefly named `deepwiki`; it's now [`forge-auto`](/docs/forge-auto.md) — renamed to avoid confusion with the DeepWiki MCP, since the pipeline compiles a verified skill from source and does **not** call that MCP. `deepwiki` still works (it resolves to `forge-auto`) but prints a one-time notice. Switch your commands to `@Ferris forge-auto <repo-or-doc-url>`.

### `@Ferris onboard` returns an error

The `onboard` alias was removed. Its replacement is [`forge-auto`](/docs/forge-auto.md), which does everything `onboard` did plus auto-scope, auto-brief, and a stricter 90% quality gate. Run `@Ferris forge-auto <repo-or-doc-url>` instead.

### forge-auto halted at the Test stage

forge-auto runs Test Skill with a stricter **90% quality threshold** (vs the default 80%), so a skill that scores below 90% halts at TS with a gap report rather than exporting a weak skill. Run `@Ferris US` to address the gaps it lists, then `@Ferris TS EX` to re-test and export. If 90% is stricter than you need, run the individual workflows or `forge` instead, which use the default threshold.

### "Inventory scan unreliable"

Surfaced by Verify Stack and Refine Architecture (exit `7`, `inventory-unreliable`) when warnings make up more than one in five of their skills plus warnings: a `metadata.json` or version folder SKF cannot read, a skill SKF generated with no `SKILL.md` or no exports found in `metadata.json`, `references/` or `SKILL.md`, or a `composes` cycle. Skills SKF did not generate, such as a module's own skills in a shared `skills_output_folder`, are listed once as "Skipped (not SKF output)" and never count. A `metadata.json` SKF cannot read counts whoever made the skill, because SKF then cannot tell whether it generated that skill.

**Fix:** the message names each warning. Re-save an unreadable `metadata.json` as a plain UTF-8 JSON object, without comments or a byte-order mark, or restore it from version control; when another tool owns that skill and needs the file as it is, move the skill out of `skills_output_folder`. Regenerate a skill whose exports are missing with the workflow that made it (`@Ferris CS <name>`, or `@Ferris QS` for a Quick Skill). Then re-run.

### "`<name>` is not SKF output"

Surfaced when create-skill, quick-skill or create-stack-skill would write a new version into a skill folder that already exists, when update-skill, export-skill, audit-skill or test-skill would move a flat skill into the versioned layout, or when drop-skill would delete or rename-skill would rename a skill, and that folder in `skills_output_folder` is one SKF did not generate, such as a BMad module's own skills or skills installed from another tool. SKF only writes into, migrates, renames or purges a skill whose `metadata.json` carries the SKF marker, so the workflow stops before it changes anything. Drop and rename also refuse a skill folder that mixes SKF output with other files, and rename and the three writers refuse a skill that is still in the old flat layout (`flat-layout`). Drop and rename check the skill's folder in `forge_data_folder` too: they refuse one that mixes SKF's brief and reports with other files (rename also refuses one that is a link, is not a folder, or cannot be listed), and leave a folder there SKF did not generate, such as another tool's folder of the same name, where it is; drop names it as "Left in place (not SKF output)". Verify Stack, Refine Architecture and compose-mode Stack Skill never stop on such skills: they list them once as "Skipped (not SKF output)" and count them toward no inventory check, unless SKF cannot read a skill's `metadata.json` (see "Inventory scan unreliable").

**Fix:** a `skills_output_folder` shared with skills from elsewhere is supported, and SKF leaves the skills it did not generate alone, so manage `<name>` yourself (to remove it, delete its folder). For create-skill, set a different `name` in the brief to create the skill beside that folder; for create-stack-skill, choose a different `project_name`; Quick Skill names a skill after its target, so use Brief Skill and Create Skill to pick another name. If the entries SKF names are in `forge_data_folder/<name>/`, move your own files out of that folder (for a link, replace it with the folder it points to; for a path that is not a folder or cannot be listed, move it out of the way or fix its permissions), then re-run. Relocate only when the folder holds a module's own source rather than skills: then set `skills_output_folder` in `_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there, and re-run `/skf-setup`. If SKF did generate the skill and its `metadata.json` was edited or lost, restore that file; if the message says SKF cannot read it (for example `Unexpected UTF-8 BOM`), re-save it as plain UTF-8. For `flat-layout`, run `@Ferris TS <name>` once to move the skill into the versioned layout, then re-run the workflow that stopped. If the entries SKF names include a version folder with no `metadata.json`, an interrupted update-skill, create-skill, quick-skill or create-stack-skill run may have left it: delete that folder, then re-run the workflow. An entry named `<version>/<entry>` is a file or folder placed inside an SKF version folder: move it out of `<name>/<version>/`, then re-run.

**`<name>` still uses the flat layout:** update-skill `--detect-only` and `--dry-run` never move a skill, but they need the versioned layout, so they stop on an SKF skill that is still flat. Run `@Ferris US <name>` once without the flag (or AS, TS or EX) to move it into the versioned layout, then re-run with the flag.

**Skills an earlier SKF already moved:** an SKF release without this check could move a module's flat skill into `<name>/<version>/<name>/` and add an `active` link. Recover it from version control: `git status` shows what moved, `git restore <skills-folder>/<name>` brings back the original files, and you then delete the `<version>/` folder and `active` link that SKF added. The same recovery applies when an SKF release without this check wrote a new version into such a folder: delete the `<version>/` folder and `active` link it added, and restore any file it replaced with `git restore`. Until then, `/skf-setup` keeps those skills in the ccc index while no marked SKF version sits in them, since they carry no SKF marker, and warns when the folder holds no SKF output at all.

**`skills_output_folder` or `forge_data_folder` set to `_bmad-output`:** create-skill stages a skill in `_bmad-output/.skf-stage/<name>/` before it writes the version. An earlier SKF release staged it in `_bmad-output/<name>/`, which with this setting is also the skill's folder or its forge folder, and left `SKILL.md`, `metadata.json`, `context-snippet.md`, `references/`, `evidence-report.md` and `provenance-map.json` at the root of that folder. That leftover can make create-skill stop with `flat-layout`, and make drop and rename refuse the skill folder or its forge folder as one that holds entries SKF did not generate. Delete those leftovers yourself and keep everything else in the folder, such as the `<version>/` folders, the `active` link and `skill-brief.yaml`; when the folder holds nothing but the leftovers, delete it whole. Then re-run.

### Update Skill stops with `blocked` before detecting changes

Surfaced by `@Ferris US` for a skill built from a remote repository (under `--headless`, `error.phase` is `init:source-tree`). Update Skill reads the commit the skill's `source_ref` points to now — or the tag, branch or commit passed with `--target-ref` — so every step compares the skill with one known commit. It stops before comparing anything when it cannot get that commit, and `error.reason` says why:

- `ref-not-found`: the ref no longer exists upstream. `invalid-ref`: the ref is not a valid tag or branch name.
- `upstream-unreachable`: the repository cannot be reached, and either `--target-ref` was passed (it always needs the network) or the skill's pinned commit is not on this machine.
- `fetch-failed` or `checkout-failed`: git could not fetch or check out the commit, for example after a dropped connection or on a full disk.
- `timed-out`: reading the commit did not finish within the time limit Update Skill gives it; a first fetch of a large repository is slow.
- `tree-folder-failed`: no folder for the checkout could be created, neither in SKF's own cache folder nor in the system temp folder.
- `git-unavailable`: `git` is not installed. `helper-failed`: `skf-source-tree.py` is missing, or it was stopped before it printed a result.
- `target-ref-needs-remote-source`: `--target-ref` was passed for a skill built from a local folder or from documentation only.

**Fix:** for `upstream-unreachable`, `fetch-failed` or `timed-out`, check your network and your access to the repository, then re-run. For `checkout-failed` or `tree-folder-failed`, free disk space and check that you can write to those folders. Install `git` for `git-unavailable`, and re-install SKF for `helper-failed`. When the tag or branch was deleted or renamed upstream, pass the one to use with `--target-ref <tag|branch|HEAD>`; the skill then records it as its `source_ref`. When only the network is down, `--target-ref` was not passed and the pinned commit is on this machine, Update Skill does not stop: it compares that commit, and its report and `warnings[]` say that upstream changes were not checked (`source-not-fetched`).

If Test Skill stops with `workspace-drift` right after an update, the update's report says why the source Test Skill reads was not brought to the commit the update recorded (`workspace-clone-not-updated`) and gives the commands that bring it there once no other skill needs it where it is. The checkout Test Skill's own message suggests does not reach a new commit of a branch or of `HEAD`.

### Update Skill stops with `halted-for-write-failure` because the version already exists

Surfaced by `@Ferris US` (under `--headless`, `error.phase` is `merge:new-version-folder`). An update that writes produces a new version of the skill in a folder of its own — for a skill built from a remote repository, the source's version when it is higher; otherwise the next patch version — and never overwrites an existing one. It updates the version the skill's `active` link names, so a second update before an export builds on the first. It stops before writing anything when `<skills_output_folder>/<name>/<version>/` or `<forge_data_folder>/<name>/<version>/` already exists. The version it updates is unchanged.

**Fix:** if an earlier update stopped after creating that version, delete both folders (whichever exist) by hand, then re-run. If you keep that version on purpose, move both folders out of the way by hand before updating. Never remove the version the `active` link names. Drop Skill removes a single version only when the export manifest lists it (`@Ferris DS <name>`, choosing that version, with `--purge`); for a skill that was never exported it can only drop every version, and a soft drop keeps the files on disk.

### My campaign stopped partway — how do I resume?

Campaign is designed for exactly this. State lives in `_campaign-state.yaml` on disk, so context death, a session timeout, or a machine restart loses nothing. Run `@Ferris campaign resume` — Ferris validates the state file, skips completed skills, and picks up from the next incomplete skill in dependency order. If the state file is corrupted, Ferris falls back to the `.bak` copy automatically. To re-process one specific skill, use `@Ferris campaign resume --from=<skill>`.

---

## Still stuck?

1. Run `@Ferris SF` to check your tool availability and current tier
2. Check `forge-tier.yaml` in your forger sidecar for your configuration
3. If `/bmad-help` is installed (via full BMAD Method), run it and describe your state — e.g. `/bmad-help my batch creation failed halfway, how do I resume?`
4. [File an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — SKF's [health check system](/docs/workflows.md#terminal-step-health-check) is the primary feedback channel, and manual issues feed the same pipeline

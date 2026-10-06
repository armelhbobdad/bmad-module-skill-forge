---
title: Troubleshooting
description: Common Skill Forge errors and how to fix them, from setup and tiers to skill ownership, updates, renames, Tessl Review and campaigns.
---

If something isn't working, start here. For general setup help see [Getting Started → Need help?](/docs/getting-started.md#need-help).

---

## Common errors

### "Setup cannot proceed: `uv` is not installed"

Setup checks for `uv` when it starts, before it detects your tools or writes anything. SKF's helper scripts use `uv` to install the Python packages they need; plain `python3` skips that and later fails with `ModuleNotFoundError: No module named 'yaml'`. So setup stops at once with one clear message instead of failing partway through. Under `--headless` or `--quiet`, the same message arrives as the `error.reason` of an `SKF_SETUP_RESULT_JSON` line whose `status` is `"blocked"`. The helper that builds that line needs only the Python standard library, so setup uses the first of `python3`, `python` or `py -3` that runs on the machine. With none of them, the run's one line is the message alone. Pipelines should treat a run with no `SKF_SETUP_RESULT_JSON` line as a failure.

**Fix:** install `uv` from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`. `uv` is documented as a runtime prerequisite in [Getting Started → Prerequisites](/docs/getting-started.md#prerequisites-full-reference).

### "Setup cannot proceed: the SKF config file was not found"

Surfaced by `/skf-setup` when the SKF install config, `_bmad/skf/config.yaml`, is missing, usually because you ran `/skf-setup` from a folder where SKF is not installed. The check runs before setup writes anything. Under `--headless` or `--quiet`, the same message arrives as the `error.reason` of an `SKF_SETUP_RESULT_JSON` line whose `status` is `"blocked"`, but only when SKF's scripts are installed in the project and `uv` or a Python interpreter can run them. Usually they are not (the folder is not an SKF project, or the install lost its scripts), so nothing can build that line and the run's one line is the message alone. Pipelines should treat a run with no `SKF_SETUP_RESULT_JSON` line as a failure.

Ferris makes the same check before he greets you and stops with "Cannot initialize. SKF is not installed in this project". Neither setup nor Ferris can fix this: setup reads the file and never writes it, and only the installer does, so both messages name the installer command below.

**Fix:** from the project root, run `npx bmad-module-skill-forge install` (or `npx bmad-method install` and add SKF as a custom module; see [Getting Started → Install](/docs/getting-started.md#install)), then re-run `/skf-setup`, or start Ferris again and give him SF. If you are in the right project but the file was deleted, restore it from version control or re-run the SKF installer. The installer also puts back SKF's scripts and knowledge files: Ferris stops with "Cannot initialize. SKF's scripts are missing from this project" when the config is there but the scripts are not, and KI says so when the knowledge index is missing. If the file exists but is malformed, setup stops with the same message Ferris shows instead: Ferris names the file and the parser error ("YAML parse error in ..."), so open `_bmad/skf/config.yaml` and repair the YAML. If its `sidecar_path` is missing or still holds a placeholder, both stop with the value to set.

### Forge reports ast-grep is unavailable

If setup reports that ast-grep was not detected, install it to unlock the Forge tier: <https://ast-grep.github.io>. Re-run `@Ferris SF` afterward and your tier upgrades automatically. If `tier_override` is set in `_bmad/_memory/forger-sidecar/preferences.yaml`, setup keeps that tier instead; set it to `~` to use the detected one.

### "No skill brief found"

Create Skill (`CS`) always needs a skill brief. Given a skill name, it loads `<forge_data_folder>/<skill-name>/skill-brief.yaml`; given a path, it loads that brief file. Run with no brief path, skill name or `--batch`, it loads the only brief in `forge_data_folder` and names it in its banner, and with several briefs there it asks which one to compile. A headless run that finds several stops with exit code 2 (`brief-missing`) and names them: pass the brief's path or skill name, or `--batch` to compile them all. "No skill brief found" means the brief you named does not exist or, with nothing named, that `forge_data_folder` holds no brief.

**Fix:** run `@Ferris BS` to write a brief (or `@Ferris AN` to get recommended briefs for a large repo), then run `@Ferris CS <skill-name>`. To make a skill without a brief, use `@Ferris QS` instead.

### "Ecosystem match found"

No run stops here today. Quick Skill has a step that checks for an official skill that already covers your source, but agentskills.io offers no registry API to ask, so the step skips the check and Quick Skill goes straight on to extraction. Create Skill has no such check since 3.0.0. Once a registry API lists an official skill for your source, Quick Skill will show it with three choices: **[P] Proceed** compiles your own skill anyway, for a different scope or custom content; **[I] Install** stops so you can install the official skill instead; **[A] Abort** cancels. A headless run will pick **[P]**. When you already know of an official skill that fits your needs, installing it with `npx skills add <skill-name>` is usually the better choice, because the library's maintainers test it and keep it current.

### Quick-tier skills have lower confidence scores

Quick tier reads source without AST analysis, so signatures are read directly from files rather than structurally verified, and its claims carry the T1-low confidence label. Install ast-grep to upgrade to the Forge tier, where each export an ast-grep rule matches is AST-verified and labeled T1. The label follows the tool that read the export, not the tier: an export ast-grep cannot match, because it cannot parse the file or no rule fits the export, is still read by eye and labeled T1-low, at Forge, Forge+ and Deep too. See [Confidence Tiers](/docs/concepts.md#confidence-tiers-t1t1-lowt2t3).

### Want semantic discovery for large codebases?

Install [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) (the `ccc` command) alongside ast-grep to unlock the Forge+ tier, then re-run `@Ferris SF`. CCC indexes your codebase and ranks its files by meaning, so a step that reads files one at a time reads the most relevant ones first, which helps most on projects with 500+ files. The ast-grep recipe runner reads every file in scope either way.

### `git status` lists a `.cocoindex_code` folder inside a source folder

When ccc is available (Forge+, or Deep with ccc), create-skill indexes the skill's source with it. A local source folder inside your project or inside another git checkout (a subfolder such as `./packages/lib`, a linked worktree or a submodule) becomes a ccc project of its own, and ccc does not gitignore an index there. create-skill keeps it out of git by writing a `.gitignore` holding `*` inside that `.cocoindex_code/` folder, and says so in one line; it never edits your own `.gitignore`. For a folder an earlier SKF release left untracked, run create-skill for that source again, or create `<source>/.cocoindex_code/.gitignore` holding the single line `*`. If you already committed the index, `git rm -r --cached <source>/.cocoindex_code` stops tracking it.

### Setup says the CCC index failed

Surfaced by `@Ferris SF` when ccc is available and `ccc index` exits with an error: the forge status shows `indexing failed, semantic discovery unavailable this session` with ccc's own message. Setup still finishes at your tier; only semantic discovery is off until the index builds. One cause is an index that an older ccc wrote and the installed ccc cannot read, with a message such as `Failed to deserialize pickle payload`.

**Fix:** from the project root, run `ccc reset`, then `ccc daemon restart`, then re-run `@Ferris SF`. `ccc reset` deletes only the index databases and keeps `.cocoindex_code/settings.yml` with SKF's exclusions. Restart the daemon before indexing again: it still holds the databases `ccc reset` deleted, so an index built right after the reset can fail with `environment already open in this program`.

### `@Ferris deepwiki` shows a deprecation notice

The auto pipeline was briefly named `deepwiki`; it's now [`forge-auto`](/docs/forge-auto.md). It was renamed to avoid confusion with the DeepWiki MCP server, since the pipeline compiles a verified skill from source and does **not** call that server. `deepwiki` still works (it resolves to `forge-auto`) but prints a one-time notice. Switch your commands to `@Ferris forge-auto <repo-or-doc-url>`.

### `@Ferris onboard` returns an error

The `onboard` alias was removed. Its replacement is [`forge-auto`](/docs/forge-auto.md), which does everything `onboard` did plus auto-scope, auto-brief, and a stricter 90% quality gate. Run `@Ferris forge-auto <repo-or-doc-url>` instead.

### Test Skill stops with `workspace-drift`

Test Skill checks a skill against the source commit it was made from. When the source folder's git checkout is at a different commit from the one the skill records (`source_commit` in its `metadata.json`), the results would show false gaps, so Test Skill stops before it writes a report.

**Fix:** check out the pinned commit the message shows with `git -C <source> checkout <pinned commit>`, then re-run `@Ferris TS <name>`. The checkout line in the message names the skill's `source_ref` when it has one. When `source_ref` is a branch, that line does not move a checkout that is already on a newer commit of the branch. To test against the source as it is now, re-run with `--allow-workspace-drift`: the findings then describe the current checkout, and a pass under that flag does not clear the skill for export until you re-test at the pinned commit. Right after an update, follow the update's report instead (see "Update Skill stops with `blocked` before detecting changes").

### forge-auto halted at the Test stage

forge-auto aims for 90%, stricter than the default 80%. A score of at least 80% but under 90% still passes, with an `evidence-report-fallback.md` that records the shortfall, unless a cap fired. TS stops the pipeline on any verdict but PASS: every FAIL (a score below 80%, a Critical or High gap at the hard gate, or a cap that turned a pass into a fail whatever the score), INCONCLUSIVE, and pass-with-drift. Run `@Ferris US <name> --from-test-report` to repair the gaps the report lists, then `@Ferris TS[<name>] EX` to test and export again (the brackets give Test Skill the skill's name). A plain `@Ferris US <name>` finds a failed or pass-with-drift test report that is newer than the skill and that no repair has applied, and offers to repair its gaps; a headless run checks the source for changes instead and adds an `unconsumed-test-report` warning. For INCONCLUSIVE, add evidence as [Pass/fail](/docs/verifying-a-skill.md#passfail) describes; for pass-with-drift, test again at the pinned commit. If 90% is stricter than you need, run the individual workflows or `forge` instead, which use the default threshold.

### "Inventory scan unreliable"

Surfaced by Verify Stack and Refine Architecture (exit `7`, `inventory-unreliable`) when there is more than one warning for every four skills SKF generated. Each of these counts as a warning: a `metadata.json` or version folder SKF cannot read, a skill SKF generated with no `SKILL.md` or no exports found in `metadata.json`, `references/` or `SKILL.md`, or a `composes` cycle. Skills SKF did not generate, such as a module's own skills in a shared `skills_output_folder`, are listed once as "Skipped (not SKF output)" and never count. A `metadata.json` SKF cannot read counts whoever made the skill, because SKF then cannot tell whether it generated that skill.

**Fix:** the message names each warning. Re-save an unreadable `metadata.json` as a plain UTF-8 JSON object, without comments or a byte-order mark, or restore it from version control; when another tool owns that skill and needs the file as it is, move the skill out of `skills_output_folder`. Regenerate a skill whose exports are missing with the workflow that made it (`@Ferris CS <name>`, `@Ferris QS` for a Quick Skill, or `@Ferris SS` for a stack skill). For a `composes` cycle, the named skills list each other, directly or through other skills, in the `composes` field of their `metadata.json`: remove the loop from one of those lists. Then re-run.

### "`<name>` is not SKF output"

SKF only writes into, migrates, renames or purges a skill whose `metadata.json` carries SKF's marker. A folder in `skills_output_folder` without that marker, such as a BMad module's own skills or skills another tool installed, makes the workflow stop before it changes anything when:

- create-skill, quick-skill or create-stack-skill would write a new version into it;
- update-skill, export-skill, audit-skill or test-skill would move a flat skill in it into the versioned layout;
- drop-skill would delete it, or rename-skill would rename it.

Drop and rename also refuse a skill folder that mixes SKF output with other files. Rename and the three writers refuse an SKF skill that is still in the old flat layout (`flat-layout`). Drop and rename check the skill's folder in `forge_data_folder` too. They refuse one that mixes SKF's brief and reports with other files, and rename also refuses one that is a link, is not a folder, or cannot be listed. A folder there that SKF did not generate, such as another tool's folder of the same name, stays where it is, and both list it as "Left in place (not SKF output)". Verify Stack, Refine Architecture and compose-mode Stack Skill never stop on such skills. They list them once as "Skipped (not SKF output)" and leave them out of every inventory check, unless SKF cannot read a skill's `metadata.json` (see "Inventory scan unreliable").

**Fix:** a `skills_output_folder` shared with skills from elsewhere is supported, and SKF leaves the skills it did not generate alone, so manage `<name>` yourself (to remove it, delete its folder). For create-skill, set a different `name` in the brief to create the skill beside that folder; for create-stack-skill, pass another `stack_name` (or choose a different `project_name`); Quick Skill names a skill after its target, so use Brief Skill and Create Skill to pick another name. If the entries SKF names are in `forge_data_folder/<name>/`, move your own files out of that folder (for a link, replace it with the folder it points to; for a path that is not a folder or cannot be listed, move it out of the way or fix its permissions), then re-run. Relocate only when the folder holds a module's own source rather than skills: then set `skills_output_folder` in `_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there, and re-run `/skf-setup`. If SKF did generate the skill and its `metadata.json` was edited or lost, restore that file; if the message says SKF cannot read it (for example `Unexpected UTF-8 BOM`), re-save it as plain UTF-8. For `flat-layout`, run `@Ferris TS <name>` once to move the skill into the versioned layout, then re-run the workflow that stopped. If the entries SKF names include a version folder with no `metadata.json`, an interrupted update-skill, create-skill, quick-skill or create-stack-skill run may have left it: delete that folder, then re-run the workflow. An entry named `<version>/<entry>` is a file or folder placed inside an SKF version folder: move it out of `<name>/<version>/`, then re-run.

**`<name>` still uses the flat layout:** update-skill `--detect-only` and `--dry-run` never move a skill, but they need the versioned layout, so they stop on an SKF skill that is still flat. Run `@Ferris US <name>` once without the flag (or AS, TS or EX) to move it into the versioned layout, then re-run with the flag.

**Skills an earlier SKF already moved:** an SKF release without this check could move a module's flat skill into `<name>/<version>/<name>/` and add an `active` link. Recover it from version control: `git status` shows what moved, `git restore <skills-folder>/<name>` brings back the original files, and you then delete the `<version>/` folder and `active` link that SKF added. The same recovery applies when an SKF release without this check wrote a new version into such a folder: delete the `<version>/` folder and `active` link it added, and restore any file it replaced with `git restore`. Until you recover them, `/skf-setup` keeps those skills in the ccc search index as long as none of their version folders carries the SKF marker. It warns when the skills folder holds no SKF output at all.

**`skills_output_folder` or `forge_data_folder` set to `_bmad-output`:** create-skill stages a skill in `_bmad-output/.skf-stage/<name>/` before it writes the version. An earlier SKF release staged it in `_bmad-output/<name>/`, which with this setting is also the skill's folder or its forge folder, and left `SKILL.md`, `metadata.json`, `context-snippet.md`, `references/`, `evidence-report.md` and `provenance-map.json` at the root of that folder. That leftover can make create-skill stop with `flat-layout`, and make drop and rename refuse the skill folder or its forge folder as one that holds entries SKF did not generate. Delete those leftovers yourself and keep everything else in the folder, such as the `<version>/` folders, the `active` link and `skill-brief.yaml`; when the folder holds nothing but the leftovers, delete it whole. Then re-run.

### Rename Skill stops with `verify-failed`

Surfaced by `@Ferris RS` (exit `5`) when the old name is still in the renamed skill's files. Before it deletes anything, rename checks each version's `SKILL.md` frontmatter, `metadata.json`, `context-snippet.md` and `provenance-map.json` for the old name as a whole name: a longer name that contains it, such as `<old>-kit`, does not count. In the two JSON files it skips the values of `source_repo`, `source_root`, `source_commit`, `source_ref`, `source_package` and `source_library`: they name the source the skill was made from, not the skill, and rename leaves them as they are. On a match it removes the new folders and stops, so the skill keeps its old name and every file as it was. The message names each file and line.

Rename rewrites the skill's `name` fields, the name where the snippet template writes it (the header, the `|IMPORTANT:` line and the `root:` path) and paths into the skill's own folders, such as a test report path an update run recorded. It leaves every other mention, because there the old name may mean something other than the skill. The source values above and the paths of files in the source stay as they are even when they look like a path into the skills folder, as in a repository that keeps its packages under `skills/<name>/`.

**Fix:** match the line the message names:

- **The skill is named after its library or repository**, as Quick Skill names a skill, and a value that rename does not skip names the library or the repository: the `description` in the `SKILL.md` frontmatter or in `metadata.json`, an export that has the library's name, the path of a file in the source such as `skills/<name>/scripts/fill.py`, or, for a skill named like its repository, the README URL create-skill records in `metadata.json` `doc_sources`. A rename does not rename the library. Such a skill cannot be renamed. Create it again under the new name with Brief Skill and Create Skill.
- **A note an earlier run wrote in its own words**, such as an `update_source` value in `metadata.json` that names the skill: edit or remove it in the old skill's file, then re-run the rename.
- **A `context-snippet.md` line other than the header, `|IMPORTANT:` and `root:`** names the skill, for example its `|gotchas:` text: edit that line in the old skill's snippet, then re-run. When the old name is a label or fixed word of the snippet template itself (`api`, `root`, `data`), the skill cannot be renamed; create it again under the new name.

### Rename Skill stops with `halted-for-concurrent-run`

Surfaced by `@Ferris RS` (exit `5`) when another rename of the same skill holds its run lock, `.skf-rename-<name>.lock` in `forge_data_folder`, and the lock has not gone stale (60 minutes after it was taken or renewed). A rename that waited at a question past that time stops the same way before it copies anything, because another rename may have run in the meantime. `--dry-run` takes no lock.

**Fix:** wait until the other rename ends, then run the rename again. If no rename of that skill is running, delete the lock file the message names, or wait until the time it gives.

### Rename Skill stops with `name-collision` and lists old folders

Surfaced by `@Ferris RS` (exit `5`) when an earlier rename of the skill to the same new name stopped after it moved the export manifest entry to the new name, but before it deleted the old folders. The new name is now the renamed skill. The message lists the old folders still on disk, and the run changes nothing.

**Fix:** if you do not want to keep the old skill, run the checked delete the message gives (`skf-skill-inventory.py guarded-delete` with those folders), then run `@Ferris EX` to rebuild the context files that may still name the old skill. A `name-collision` without that list means the new name is already in use: pick another one.

### Update Skill stops with `blocked` before detecting changes

Surfaced by `@Ferris US` for a skill built at Forge tier or above from a remote repository, or when `--target-ref` is passed for any other skill (under `--headless`, `error.phase` is `init:source-tree`). Update Skill reads the commit that the skill's `source_ref` points to now, or the tag, branch or commit passed with `--target-ref`, so every step compares the skill with one known commit. It stops before comparing anything when it cannot get that commit, and `error.reason` says why:

- `ref-not-found`: the ref no longer exists upstream. `invalid-ref`: the ref is not a valid tag or branch name.
- `upstream-unreachable`: the repository cannot be reached, and either `--target-ref` was passed (it always needs the network) or the skill's pinned commit is not on this machine.
- `fetch-failed` or `checkout-failed`: git could not fetch or check out the commit, for example after a dropped connection or on a full disk.
- `timed-out`: reading the commit did not finish within the time limit Update Skill gives it; a first fetch of a large repository is slow.
- `tree-folder-failed`: no folder for the checkout could be created, neither in SKF's own cache folder nor in the system temp folder.
- `git-unavailable`: `git` is not installed. `helper-failed`: `skf-source-tree.py` is missing, or it was stopped before it printed a result.
- `target-ref-needs-remote-source`: `--target-ref` was passed for a skill built from a local folder, from documentation only, or at Quick tier.

**Fix:** for `upstream-unreachable`, `fetch-failed` or `timed-out`, check your network and your access to the repository, then re-run. For `checkout-failed` or `tree-folder-failed`, free disk space and check that you can write to those folders. Install `git` for `git-unavailable`, and re-install SKF for `helper-failed`. When the tag or branch was deleted or renamed upstream, pass the one to use with `--target-ref <tag|branch|HEAD>`; the skill then records it as its `source_ref`. When only the network is down, `--target-ref` was not passed and the pinned commit is on this machine, Update Skill does not stop: it compares that commit, and its report and `warnings[]` say that upstream changes were not checked (`source-not-fetched`).

If Test Skill stops with `workspace-drift` right after an update, the update's report says why the source that Test Skill reads was not moved to the commit the update recorded (`workspace-clone-not-updated`). It also gives the `git` commands that move it there once no other skill needs it where it is. Use those commands, not the `git checkout` that Test Skill's own message suggests: for a branch or `HEAD`, that checkout does not reach the new commit.

### Update Skill stops with `halted-for-write-failure` because the version already exists

Surfaced by `@Ferris US` (under `--headless`, `error.phase` is `merge:new-version-folder`). An update that writes puts the new version of the skill in a folder of its own and never overwrites an existing one. The new version is the source's version when the skill was built from a remote repository and that version is higher; otherwise it is the next patch version. It updates the version the skill's `active` link names, so a second update before an export builds on the first. It stops before writing anything when `<skills_output_folder>/<name>/<version>/` or `<forge_data_folder>/<name>/<version>/` already exists. The version it updates is unchanged.

**Fix:** if an earlier update stopped after creating that version, delete both folders (whichever exist) by hand, then re-run. If you keep that version on purpose, move both folders out of the way by hand before updating. Never remove the version the `active` link names. Drop Skill removes a single version only when the export manifest lists it (`@Ferris DS <name> --mode purge`, choosing that version); for a skill that was never exported it can only drop every version, and a soft drop (`--mode deprecate`) keeps the files on disk.

### Update Skill stops with `halted-for-concurrent-run`

Surfaced by `@Ferris US` when another update of the same skill holds its run lock, `.skf-update.lock` in `<forge_data_folder>/<name>/` (under `--headless`, `error.phase` is `init:concurrency-guard`). The message names the update that holds the lock, the lock file, and when the lock goes stale (60 minutes after it was taken or renewed). `--detect-only` and `--dry-run` take no lock.

**Fix:** wait until the other update ends, then re-run. If no update of that skill is running (a session that crashed or was closed leaves its lock behind), delete the lock file the message names, or wait until the time it gives. An update that finds a stale lock takes it over and undoes what the interrupted update left half written.

**`run-lock-lost`:** the same status with this reason means the update waited at a question past the stale time, so another update may have changed the skill (`error.phase` is `merge:run-lock` or `write:run-lock`). It stops before it writes `metadata.json`, and the halt undoes anything the update already wrote: it removes the new version folders, or, for a repair from a test report, restores the files it edited in place from the copy it took first, and the message says which. Re-run the update once no other update of that skill runs; if a version folder the message names is still on disk, delete it first.

### A report says `Tessl Review: off`, `not run`, `no result` or `failed`

Create Skill and Test Skill record one `Tessl Review:` line in the evidence report and the test report. Tessl Review is optional and never stops a run, so the line says why it produced no score:

| Status | What it means and what to do |
|---|---|
| `off` | The default. Set `tessl_review_workspace` in `_bmad/_memory/forger-sidecar/preferences.yaml` to the name of one of your Tessl workspaces (`tessl workspace list` shows them) to enable it. The review uploads the skill's `SKILL.md`, `references/`, `scripts/` and `assets/` to Tessl, where it stays in that workspace's history, and each fresh review spends Tessl credits. |
| `invalid-config` | `tessl_review_workspace` is set to something that is not a workspace name, such as `true`, a value with spaces or one with characters other than letters, digits, `.`, `_` and `-`. Set it to the workspace name, or to `~` to turn the review off. |
| `not-installed` | Neither `tessl` nor a cached npm copy of it was found. Install the Tessl CLI (see [tessl.io](https://tessl.io)); SKF never installs it. |
| `signed-out` | Run `tessl login`, or set `TESSL_TOKEN` for an unattended run. |
| `command-unavailable` | The installed tessl has no working `tessl review run`. Update tessl. |
| `pending` | The workflow stopped checking before Tessl finished. The review may still complete on Tessl's side: `tessl review view <run id>` shows it (the line names the run id); re-run the workflow later. |
| `unknown-run` | Tessl has no review with the run id the workflow checked, or the workflow passed something that is not a run id. Re-run the workflow; `tessl review list` shows your reviews. |
| `timeout` | The workflow did not see Tessl finish while it waited (about ten minutes): Tessl was still working, or the last checks failed or did not answer. The review may still complete on Tessl's side: `tessl review view <run id>` shows it (the line names the run id); re-run the workflow later. |
| `failed` | The line carries tessl's own message, a skill file SKF could not read, or a tessl call that did not answer in time. When it is about the workspace, check the name against `tessl workspace list`. `did not answer within` means tessl was slow, for example while its npm launcher downloads tessl on a first run: re-run the workflow. `stopped before skf-tessl-review.py reported a result` means your agent's shell tool stopped a helper call; when Tessl had accepted the review, the report names its run id for `tessl review view <run id>`. |
| `parse-failure` | tessl printed no review SKF can read. Update tessl, or run `tessl review run <skill-folder> --json` yourself to see its output. |

When Tessl Review produces no score, Test Skill's External Validation uses skill-check's score alone.

### "Description sanitization failed"

Create Skill checks the staged skill's frontmatter `description` for `<` and `>` before it writes the skill, because the Claude platform does not accept XML tags there. When it finds them, it replaces them with `{` and `}` and checks again; this message means they were still there after that, so nothing was written to `skills_output_folder`. Under `--headless` the stderr envelope carries `halt_reason: "description-angle-brackets"`.

**Fix:** check that `_bmad-output/.skf-stage/<name>/SKILL.md` can be written (its permissions, and no other program holding it open), then re-run `@Ferris CS`. To keep angle brackets out of the description from the start, write placeholders in the brief as `{name}` or `NAME` rather than `<name>`.

### My campaign stopped partway: how do I resume?

Campaign is designed for exactly this. Its state lives on disk in `_campaign-state.yaml` (by default in `forge-data/_campaign/`), so context death, a session timeout, or a machine restart loses nothing. Run `@Ferris campaign resume`. Ferris validates the state file, skips completed skills, and picks up from the next incomplete skill in dependency order. If the state file is corrupted, Ferris restores the `.bak` copy automatically when that copy is valid; when neither file is usable, it stops and shows both errors. To process one specific skill again, use `@Ferris campaign resume --from=<skill>`; for a skill that already finished, choose **[R]e-run** when asked.

---

## Still stuck?

1. Run `@Ferris SF` to check your tool availability and current tier
2. Check `_bmad/_memory/forger-sidecar/forge-tier.yaml` for the tools setup detected and your current tier
3. If `/bmad-help` is installed (via full BMAD Method), run it and describe your state, for example `/bmad-help my batch creation failed halfway, how do I resume?`
4. [File an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). SKF's [health check system](/docs/workflows.md#terminal-step-health-check) is the main way SKF collects feedback, and issues you file by hand reach the same place.

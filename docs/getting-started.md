---
title: Getting Started
description: Install Skill Forge and generate your first verified skill in under a minute.
---

## In 60 seconds

One command. One verified skill. Here's what an instruction in a cognee skill looks like:

```python
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L27]
    query_text="What does Cognee do?"
)
```

Every instruction carries a receipt: the file and line in the upstream repo it came from. `AST` means ast-grep matched the definition there; an export SKF read by eye instead carries an `[SRC:...]` receipt and a lower confidence label. The skill's `metadata.json` records the commit SHA those lines were read at. Your AI reads these instead of guessing from training data, and you can open the source at that commit to confirm the function exists. Nothing is made up, and everything can be checked.

Want to see the full audit on a real shipped skill before you install anything? → [Verifying a Skill](/docs/verifying-a-skill.md).

---

## Install

One command, on any platform. Requires Node.js ≥ 22, Python ≥ 3.11, and `uv` ([full tool matrix below](#prerequisites-full-reference)).

```bash
npx bmad-module-skill-forge install
```

You'll be asked for a project name, where to save your skills and SKF's workspace files, which IDEs to configure, and whether to add the learning material (a copy of these docs in `_skf-learn/`). The installer puts SKF in `_bmad/skf/` and copies its skills to each IDE's skills folder (for example `.claude/skills/` or `.cursor/skills/`), so your IDE loads them natively.

### As a custom module during BMAD Method installation

```bash
npx bmad-method install
```

Step through the installer prompts:

- **"Do you want to install custom or community modules (Git URL or local path)?"**: Yes
- **"Git URL or local path:"**: paste the SKF repo URL:

```
https://github.com/armelhbobdad/bmad-module-skill-forge
```

Or, if you've already cloned the repo locally, provide the path to the repo root instead:

```
/path/to/bmad-module-skill-forge
```

This installs BMAD core + SKF together with full IDE integration, manifests, and help catalog. Best when you want the complete BMAD development workflow. See [BMAD Synergy](/docs/bmad-synergy.md) for how SKF workflows pair with the phases of BMM (BMAD's software development module) and other BMAD modules.

### Add SKF to an existing BMAD project

If you already have BMAD installed, you can add SKF afterward by running the standalone installer in the same directory:

```bash
npx bmad-module-skill-forge install
```

The installer detects the existing `_bmad/` directory and installs SKF alongside your current modules. See [BMAD Synergy](/docs/bmad-synergy.md) for integration patterns with your existing BMM workflows.

### Updating an existing SKF installation

To move to a newer (or older) SKF version, run the installer again in your project directory:

```bash
npx bmad-module-skill-forge@latest install
```

The installer reads the installed version from your manifest and shows the change in the prompt, for example `v0.10.0 → v1.0.0 available`. Pick **Update** to replace the SKF files while keeping your `config.yaml` and your forge state (tier and preferences). The option label names the direction you're moving (upgrade, reinstall of the same version, or downgrade), so you always see exactly what you're about to apply. Pick **Fresh install** to remove the installed SKF files in `_bmad/skf/` and answer the install questions again, with your previous answers filled in. Neither option touches the skills you generated or your forge state. The installer then prints its [tool report](#the-tool-report). Afterwards, run `@Ferris SF` so SKF re-detects your tools.

> The `@latest` suffix forces npx to fetch the newest published version instead of reusing a cached copy from a previous run.

### Other installer commands

Run these from your project folder:

- `npx bmad-module-skill-forge@latest update` refreshes SKF files without asking questions. It keeps `config.yaml` and your forge state (tier and preferences). It then prints the [tool report](#the-tool-report), followed by the update notice when a newer SKF version is published.
- `npx bmad-module-skill-forge status` shows the installation, its IDEs, your forge tier and the tools the last setup detected. Below them it prints the [tool report](#the-tool-report), which lists each tool installed now against its minimum version, with the command that upgrades it, and then the output folders.
- `npx bmad-module-skill-forge uninstall` lists what it will remove and asks first. It removes SKF, your forge state in `_bmad/_memory/forger-sidecar/`, `_skf-learn/` and the SKF skills in your IDE skill folders. It keeps the skills you generated, your `forge-data/`, and the SKF section in `CLAUDE.md`, `AGENTS.md` or `.cursorrules`.

### The tool report

After a successful `install` or `update`, and in `status`, the installer checks the tools SKF uses and prints one line per tool: the version it found and how that version compares with the tool's minimum. For example:

```
  Tools
    Node.js   24.21.0  ok
    ast-grep  0.42.2   upgrade to >= 0.45.3   npm install -g @ast-grep/cli@latest
    ccc       -        optional, Forge+ tier  https://github.com/cocoindex-io/cocoindex-code
```

Each tool reads `ok`, `upgrade to >= <minimum>` with the command that upgrades it, `missing` or `optional` with where to get it, or `installed, version unknown` when SKF cannot read its version. The minimums are the ones in the [Prerequisites](#prerequisites-full-reference) table. The check waits at most about 3 seconds for the tools to answer and never changes the command's exit code. It runs no tool from your project folder and never runs `npx`, so `tessl` and `skill-check`, which SKF runs through `npx`, read as optional when they are not installed.

A tier tool below its minimum does not count toward your tier. With an ast-grep older than 0.45.3, `@Ferris SF` leaves you at Quick, whatever else you have installed. Setup's FORGE STATUS report then shows an upgrade line for the tool, and a headless setup adds a `tool_below_minimum` warning to its `SKF_SETUP_RESULT_JSON` envelope. Upgrade the tool and run `@Ferris SF` again. A tool with no minimum, or one whose version SKF cannot read, never lowers your tier.

---

## Your first skill

**Talking to Ferris.** These docs write each command as `@Ferris <code>`, which means "ask Ferris to run this". First start Ferris in your IDE. In Claude Code, Cursor and most other IDEs, type `/skf-forger`. In Codex, type `$skf-forger`, and in Pi, `/skill:skf-forger`. Some IDEs have no command: ask to talk to Ferris and the IDE loads him. The installer prints the right command for each IDE you picked. When Ferris shows his menu, type the code, for example `SF`. Each workflow is also a skill of its own, so `/skf-setup` runs Setup Forge without the menu. To leave Ferris, say `dismiss`.

### 1. Set up your forge

```
@Ferris SF
```

This detects your tools and their versions, sets your capability tier (Quick, Forge, Forge+ or Deep, depending on which tools you have; a tool counts only at its minimum version or newer, so an ast-grep older than 0.45.3 leaves you at Quick), and initializes the forge environment. Run it once per project, and again whenever you install, upgrade or remove one of the tools listed under [Prerequisites](#prerequisites-full-reference), so SKF picks up the change.

### 2. Generate your first skill

**Zero-ceremony path (forge-auto):**
```
@Ferris forge-auto https://github.com/honojs/hono
```

One command turns a repo URL (or a doc URL) into a verified skill. It scopes the skill, writes its brief, compiles, tests and exports it, with no configuration. The test aims for a 90% score: a skill scoring 80% or more still passes, with an evidence report explaining the gap, and one below 80% stops the run. If you only read one thing, [start with forge-auto](/docs/forge-auto.md).

**Fastest path (Quick Skill):**
```
@Ferris QS https://github.com/bmad-code-org/BMAD-METHOD
```

Ferris reads the repository, extracts the public API, and generates a skill in under a minute. It is a best-effort draft: it lists the exports and usage examples but carries no receipt on each instruction, so use `forge-auto` or `forge` when you need receipts. The skill lands in your skills folder (`skills/` by default) under `<name>/<version>/<name>/`, as `SKILL.md`, `context-snippet.md` and `metadata.json`. Quick Skill stops there. To test and export the skill in the same run, use `@Ferris forge-quick <package-or-url>` instead, or run `@Ferris TS` and then `@Ferris EX`, each in a fresh session.

**Targeting a specific version:** Append `@version` to pin the skill to a library version:
```
@Ferris QS cognee@1.0.0
```

**Full quality path (pipeline mode):**
```
@Ferris forge https://github.com/cocoindex-io/cocoindex cocoindex
```

`forge` chains Brief → Create → Test → Export. It needs an explicit repo URL **and** a skill name because it starts with Brief Skill (BS), which doesn't guess targets. If you just want a fast skill from a package name, use `@Ferris forge-quick cognee` instead: that starts with Quick Skill (QS), which looks the name up on npm, PyPI or crates.io (falling back to a web search) to find its source repo.

Or one workflow per session:
```
@Ferris BS    # Brief: scope and design the skill
# (clear session)
@Ferris CS    # Create: compile from the brief
# (clear session)
@Ferris TS    # Test: verify completeness
# (clear session)
@Ferris EX    # Export: package for distribution
```

> **One workflow per session.** Each SKF workflow loads step files, knowledge fragments, and extraction data into the LLM's context as it executes. Running a second workflow in the same session can cause leftover context to interfere: stale references, mode confusion, or degraded output. Clear your session (start a new conversation) before invoking a new workflow. Pipeline mode (for example `@Ferris forge-auto` or `@Ferris forge`) runs several workflows in one session and answers each question with its default instead of stopping to ask; for manual control, start fresh between each one. Ferris keeps your forge tier and preferences on disk in `_bmad/_memory/forger-sidecar/`, so a new session loses no configuration.

### 3. Install the skill in your project

Export adds a short index of the skill to `CLAUDE.md`, `AGENTS.md` or `.cursorrules`. That index points at your IDE's skill folder, for example `.claude/skills/<name>/`. The skill itself is written to `skills/<name>/<version>/<name>/` (your `skills_output_folder`), so install it once. Export prints the command, for example:

```
npx skills add ./skills/cognee/1.0.0/cognee
```

Keep the leading `./`. Without it, the `skills` tool reads the path as a GitHub repository and fails. If your agent does not see the skill yet, reload or restart your IDE.

### 4. Stack skill (for full projects)

```
@Ferris SS
```

Analyzes your project's dependencies and generates a consolidated stack skill with integration patterns.

> **After every workflow:** Ferris runs a **health check**, a short review of the session that captures any friction, bugs, or gaps in SKF's own instructions. Clean runs exit in one line. When something went wrong, Ferris shows the findings and asks before sending anything: bugs can be filed as GitHub issues, and friction or gaps are saved to a local queue in `forge_data_folder` unless you choose to submit them too. **Please let workflows run to completion** so the health check can fire. If it was skipped, ask Ferris to run it (`@Ferris please run the workflow health check for this session`) or [open an issue directly](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). See [Workflow Health Check](/docs/workflows.md#terminal-step-health-check).

---

## Common use cases

> **Looking for end-to-end examples?** See [Examples](/docs/examples.md) for thirteen real-world scenarios with full command transcripts, from Quick Skill in under a minute to onboarding an existing codebase, stack verification, release-prep drift fixes, and docs-only skills for SaaS products.

---

## Prerequisites (full reference)

Most users only need Node.js, Python, and `uv`. The other tools unlock more capabilities, and Setup detects which ones you have and their versions, and sets your tier automatically. You can install them later: run `@Ferris SF` again afterwards and your tier goes up.

<!-- tool-requirements:start -->
<!-- Generated from src/shared/tool-requirements.yaml by `node tools/tool-requirements.js --write`: edit that file, not this table. -->

| Tool                                                                  | Used for                                                                                                                                                                                    | Minimum | Tested on    | Install                                                   |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------ | --------------------------------------------------------- |
| `Node.js`                                                             | Installation, npx commands                                                                                                                                                                  | 22      | 22, 24       | <https://nodejs.org>                                      |
| `Python`                                                              | Deterministic scoring, validation, and utility scripts. The minimum is what the helpers that read package manifests need (used by Quick Skill, Brief Skill, Analyze Source and Stack Skill) | 3.11    | 3.11, 3.12   | <https://www.python.org>                                  |
| `uv` (Python package runner)                                          | Running Python scripts with automatic dependency management                                                                                                                                 | none    | not recorded | <https://docs.astral.sh/uv/getting-started/installation/> |
| `git`                                                                 | Reading remote sources, and checking that a local source is still at the commit a skill was built from                                                                                      | 2.15    | not recorded | <https://git-scm.com/downloads>                           |
| `gh` (GitHub CLI)                                                     | Required for the Deep tier, for Campaign, and for `forge-auto --pin`. Optional otherwise, where it makes reading GitHub sources easier                                                      | none    | not recorded | <https://cli.github.com>                                  |
| `ast-grep` (CLI tool for code structural search, lint, and rewriting) | Forge, Forge+ and Deep tiers                                                                                                                                                                | 0.45.3  | 0.45.3       | <https://ast-grep.github.io>                              |
| `ccc` (cocoindex-code semantic code search)                           | Forge+ tier, and the Deep tier when installed                                                                                                                                               | none    | not recorded | <https://github.com/cocoindex-io/cocoindex-code>          |
| `qmd` (local hybrid search engine for project files)                  | Deep tier                                                                                                                                                                                   | none    | not recorded | <https://github.com/tobi/qmd>                             |
| `tessl` (Tessl CLI)                                                   | Opt-in Tessl Review in Create Skill and Test Skill (`tessl_review_workspace` in preferences)                                                                                                | none    | not recorded | <https://tessl.io>                                        |
| `skill-check` (skill validator)                                       | Spec validation, auto-fix and quality scoring. SKF runs it with npx, so it needs no install; without it, validation is done by hand                                                         | none    | not recorded | <https://github.com/thedaviddias/skill-check>             |
| `ast-grep` MCP server (recommended alongside CLI)                     | Optional in Forge, Forge+ and Deep: workflows use it when present and fall back to the CLI                                                                                                  |         |              | <https://github.com/ast-grep/ast-grep-mcp>                |
| `SNYK_TOKEN` (Snyk API token, **Enterprise plan required**)           | Optional security scan                                                                                                                                                                      |         |              | <https://docs.snyk.io/snyk-api/authentication-for-api>    |

<!-- tool-requirements:end -->

**Minimum** is the oldest version SKF supports, and **Tested on** lists the versions SKF's own runs use: CI, the install smoke test or a named release run. `none` means SKF sets no minimum for the tool yet, and `not recorded` means no SKF run has recorded a version of it yet.

Setup picks your tier from the tools it finds: Quick needs none of them, Forge needs ast-grep, Forge+ needs ast-grep and ccc, and Deep needs ast-grep, gh and qmd. A tool counts toward a tier only at its **Minimum** version or newer, so an ast-grep older than 0.45.3 leaves you at Quick (see [The tool report](#the-tool-report)).

Security scanning via Snyk is optional and requires an Enterprise plan; it does not affect your tier level.

### Platform support

**Linux and Windows** are tested automatically on every pull request. **macOS** works in practice, since it behaves like Linux for SKF's Node and Python tools, but it is not tested automatically; if you hit a macOS-specific bug, please [file an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues).

On Windows, SKF transparently falls back to NTFS junctions when symlink privilege isn't held, so no Developer Mode or admin rights are required. Git Bash (bundled with [Git for Windows](https://git-scm.com/download/win)), PowerShell, and WSL2 all work.

---

## Configuration

The installer saves two folder settings in `_bmad/skf/config.yaml`, where you can also add one optional setting by hand. SKF also reads one setting from BMAD's core config, and a few runtime preferences live in `_bmad/_memory/forger-sidecar/preferences.yaml`:

| Variable                      | Purpose                                                                                                                                                                                                                                                                  | Default                                                             |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| `skills_output_folder`        | Where generated skills are saved                                                                                                                                                                                                                                         | `{project-root}/skills`                                             |
| `forge_data_folder`           | Where SKF keeps its working files: skill briefs, test and evidence reports, and Verify Stack reports                                                                                                                                                                     | `{project-root}/forge-data`                                         |
| `output_folder`               | Where Refine Architecture (RA) saves refined architecture documents. *Inherited from BMAD Core Config.*                                                                                                                                                                  | Set by BMAD Core Config; `_bmad-output` in a standalone SKF install |
| `tier_override`               | Force a specific tier for comparison or testing (in `_bmad/_memory/forger-sidecar/preferences.yaml`)                                                                                                                                                                     | `~` (auto-detect)                                                   |
| `headless_mode`               | Skip confirmation gates in all workflows (in `_bmad/_memory/forger-sidecar/preferences.yaml`)                                                                                                                                                                            | `false`                                                             |
| `passive_context`             | Let Export Skill write `context-snippet.md` and update the SKF section in `CLAUDE.md`, `AGENTS.md` or `.cursorrules`; set to `false` to skip both (in `_bmad/_memory/forger-sidecar/preferences.yaml`)                                                                   | `true`                                                              |
| `compact_greeting`            | Have Ferris greet you briefly instead of showing the full menu when you come back (in `_bmad/_memory/forger-sidecar/preferences.yaml`)                                                                                                                                   | `false`                                                             |
| `tessl_review_workspace`      | Opt in to Tessl Review: the Tessl workspace Create Skill and Test Skill review each skill in (in `_bmad/_memory/forger-sidecar/preferences.yaml`). Uploads the skill's files to Tessl and spends Tessl credits; needs the `tessl` CLI and `tessl login` or `TESSL_TOKEN` | `~` (off)                                                           |
| `snippet_skill_root_override` | For a repo that keeps its skills in one folder such as `skills/` instead of an IDE skill folder: the path the context index points at (in `_bmad/skf/config.yaml`). When Export finds existing snippets that point elsewhere, it asks you to set it                      | unset                                                               |

**If you use ccc** (the semantic code search tool behind the Forge+ tier), setup keeps everything SKF writes to `skills_output_folder` and `forge_data_folder` out of its search index, so searches find your code rather than generated skills.

- **Sharing a folder is fine.** When `skills_output_folder` also holds folders SKF did not generate, such as skills installed from elsewhere, setup excludes only the entries SKF generated and the rest stays searchable. When the folder holds only SKF output plus loose files directly in it, those files are excluded with it, so keep your own files elsewhere.
- **Run `@Ferris SF` again after you create skills** in a shared folder, so the new ones are excluded too.
- **Keep both settings away from source you work on.** A folder with none of SKF's output stays indexed, and setup warns about it.
- **To exclude a folder yourself,** add it to `exclude_patterns` in `.cocoindex_code/settings.yml`, only for a folder SKF leaves indexed and only after setup has run with ccc installed. Setup never removes an entry it did not add, but it treats an entry identical to one of its own as its own.

Workflows also write into, move, rename or delete only the skill folders SKF generated. Before a workflow writes a new version into an existing skill folder, moves a flat skill into the versioned layout, renames a skill or deletes one, it checks that the skill's `metadata.json` carries the SKF marker, and stops before changing anything when it does not. Drop and rename also leave a folder in `forge_data_folder` that SKF did not generate where it is. Verify Stack, Refine Architecture and Stack Skill in compose mode read only the skills SKF generated and list the others once as not SKF output. See [Troubleshooting](/docs/troubleshooting.md) for the messages you may see.

**Do not add a `!` entry** to `exclude_patterns` for a path in `skills_output_folder` or `forge_data_folder`. ccc applies a `!` entry against every exclusion. While setup excludes the folder whole, even an entry that names a single file or a path that does not exist, such as `!skills/my-tool`, brings back all SKF output in the folder, each skill twice (through its version folder and its `active` link). Such an entry in a `/*` or `/**` form also brings back `node_modules` and hidden folders below it. To keep content of your own in that folder searchable, put it in a folder of its own there and re-run `/skf-setup` (`@Ferris SF`): setup then excludes only the entries SKF generated, and your content stays indexed with no `!` entry. A folder inside a folder that setup always excludes, such as `_bmad-output` or `.claude`, stays excluded whole, so keep content you want searchable outside it. Setup warns on every run while a `!` entry cancels one of its exclusions, including after that content is gone and setup excludes the folder whole again.

Setup (`@Ferris SF`) records the tools it detected, your tier and the state of your search indexes in `_bmad/_memory/forger-sidecar/forge-tier.yaml`.

---

## What's next?

- [Forge-Auto](/docs/forge-auto.md): the zero-ceremony path, one command from repo or doc URL to a verified skill
- [Campaign](/docs/campaign.md): orchestrate many coordinated skills across sessions with dependency tracking and resume
- [Agents](/docs/agents.md): learn about Ferris
- [Workflows](/docs/workflows.md): the full command reference
- [Examples](/docs/examples.md): real-world scenarios with transcripts

---

## Need help?

If you run into issues:
1. Run `/bmad-help`: it analyzes your current state and suggests what to do next
   (e.g. `/bmad-help my quick skill has low confidence scores, how do I improve them?`)
   *Provided by the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD); not available in standalone SKF installations.*
2. Run `@Ferris SF` to check your tool availability and tier
3. Check `_bmad/_memory/forger-sidecar/forge-tier.yaml` for the tools SKF detected and your current tier
4. If a workflow gave you friction, ask Ferris to run the health check for that session, or [open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). See [Workflow Health Check](/docs/workflows.md#terminal-step-health-check).

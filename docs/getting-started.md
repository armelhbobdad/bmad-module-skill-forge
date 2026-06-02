---
title: Getting Started
description: Install Skill Forge and generate your first verified skill in under a minute.
---

## In 60 seconds

One command. One verified skill. Here's a real snippet from a cognee skill SKF compiled:

```python
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L26]
    query_text="What does Cognee do?"
)
```

Every instruction carries a receipt — a file, a line, and a commit SHA from the upstream repo. Your AI reads these instead of guessing from training data, and you can open the source at the pinned commit to confirm the function exists. Nothing is made up; everything is falsifiable.

Want to see the full audit on a real shipped skill before you install anything? → [Verifying a Skill](../verifying-a-skill/).

---

## Install

One command, on any platform. Requires Node.js ≥ 22, Python ≥ 3.10, and `uv` ([full tool matrix below](#prerequisites-full-reference)).

```bash
npx bmad-module-skill-forge install
```

You'll be prompted for project name, output folders, and which IDEs to configure. The installer copies skill directories to each IDE's skills folder (e.g. `.claude/skills/`, `.cursor/skills/`) so skills are available natively.

### As a custom module during BMAD Method installation

```bash
npx bmad-method install
```

Step through the installer prompts:

- **"Would you like to browse community modules?"** — No (SKF isn't in the community catalog yet)
- **"Would you like to install from a custom source (Git URL or local path)?"** — Yes
- **"Git URL or local path:"** — paste the SKF repo URL:

```
https://github.com/armelhbobdad/bmad-module-skill-forge
```

Or, if you've already cloned the repo locally, provide the path to the repo root instead:

```
/path/to/bmad-module-skill-forge
```

This installs BMAD core + SKF together with full IDE integration, manifests, and help catalog. Best when you want the complete BMAD development workflow. See [BMAD Synergy](../bmad-synergy/) for how SKF workflows pair with BMM phases and other BMAD modules.

### Add SKF to an existing BMAD project

If you already have BMAD installed, you can add SKF afterward by running the standalone installer in the same directory:

```bash
npx bmad-module-skill-forge install
```

The installer detects the existing `_bmad/` directory and installs SKF alongside your current modules. See [BMAD Synergy](../bmad-synergy/) for integration patterns with your existing BMM workflows.

### Updating an existing SKF installation

To move to a newer (or older) SKF version, run the installer again in your project directory:

```bash
npx bmad-module-skill-forge@latest install
```

The installer reads the installed version from your manifest and shows the delta in the prompt — for example `v0.10.0 → v1.0.0 available`. Pick **Update** to replace SKF files while keeping your `config.yaml` intact. The option label adapts to the direction you're moving (upgrade, reinstall the same version, or downgrade) so you always see exactly what you're about to apply. Pick **Fresh install** instead if you want to wipe everything and start clean.

> The `@latest` suffix forces npx to fetch the newest published version instead of reusing a cached copy from a previous run.

---

## Your first skill

### 1. Setup your forge

```
@Ferris SF
```

This detects your tools, sets your capability tier, and initializes the forge environment. You only need to do this once per project.

### 2. Generate your first skill

**Zero-ceremony path (forge-auto):**
```
@Ferris forge-auto https://github.com/honojs/hono
```

One command turns a repo URL (or a doc URL) into a verified skill — auto-scope, auto-brief, a 90% quality gate, and export, with no configuration. If you only read one thing, [start with forge-auto](../forge-auto/).

**Fastest path (Quick Skill):**
```
@Ferris QS https://github.com/bmad-code-org/BMAD-METHOD
```

Ferris reads the repository, extracts the public API, and generates a skill in under a minute.

**Targeting a specific version:** Append `@version` to pin the skill to a library version:
```
@Ferris QS cognee@1.0.0
```

**Full quality path (pipeline mode):**
```
@Ferris forge https://github.com/cocoindex-io/cocoindex cocoindex
```

`forge` chains Brief → Create → Test → Export. It needs an explicit repo URL **and** a skill name because it starts with Brief Skill (BS), which doesn't guess targets. If you just want a fast skill from a package name, use `@Ferris forge-quick cognee` instead — that starts with Quick Skill (QS), which resolves packages via the registry.

Or one workflow per session:
```
@Ferris BS    # Brief — scope and design the skill
# — clear session —
@Ferris CS    # Create — compile from the brief
# — clear session —
@Ferris TS    # Test — verify completeness
# — clear session —
@Ferris EX    # Export — package for distribution
```

> **One workflow per session.** Each SKF workflow loads step files, knowledge fragments, and extraction data into the LLM's context as it executes. Running a second workflow in the same session can cause leftover context to interfere — stale references, mode confusion, or degraded output. Clear your session (start a new conversation) before invoking a new workflow. Pipeline mode chains workflows automatically with headless mode; for manual control, start fresh between each one. Sidecar state (forge tier, preferences) persists across sessions, so no configuration is lost.

### 3. Stack skill (for full projects)

```
@Ferris SS
```

Analyzes your project's dependencies and generates a consolidated stack skill with integration patterns.

> **After every workflow:** Ferris runs a **health check** — a reflection step that captures any friction, bugs, or gaps from the session. Clean runs exit in one line; when something breaks, Ferris offers to file structured findings as GitHub issues (with your approval). **Please let workflows run to completion** so the health check can fire. If it was skipped, ask Ferris to run it (`@Ferris please run the workflow health check for this session`) or [open an issue directly](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). See [Workflow Health Check](../workflows/#terminal-step-health-check).

---

## Common use cases

> **Looking for end-to-end examples?** See [Examples](../examples/) for thirteen real-world scenarios with full command transcripts — from Quick Skill under a minute, to brownfield onboarding, stack verification, release-prep drift remediation, and SaaS docs-only skills.

---

## Prerequisites (full reference)

Most users only need Node.js, Python, and `uv` — the rest unlock additional capabilities but SKF detects what's available and sets your tier automatically. You can install them later; your tier upgrades when you do.

| Tool                                                                   | Required For                                                                          | Install                                                   |
|------------------------------------------------------------------------|---------------------------------------------------------------------------------------|-----------------------------------------------------------|
| `Node.js` >= 22                                                        | Installation, npx commands                                                            | <https://nodejs.org>                                      |
| `Python` >= 3.10                                                       | Deterministic scoring, validation, and utility scripts                                | <https://www.python.org>                                  |
| `uv` (Python package runner)                                           | Running Python scripts with automatic dependency management                           | <https://docs.astral.sh/uv/getting-started/installation/> |
| `gh` (GitHub CLI)                                                      | Required for Deep mode. Optional convenience in Quick/Forge/Forge+ for source access. | <https://cli.github.com>                                  |
| `ast-grep`  (CLI tool for code structural search, lint, and rewriting) | Forge + Deep modes                                                                    | <https://ast-grep.github.io>                              |
| `ast-grep` MCP server (recommended alongside CLI)                      | Forge + Deep modes                                                                    | <https://github.com/ast-grep/ast-grep-mcp>                |
| `ccc` (cocoindex-code semantic code search)                            | Forge+ mode                                                                           | <https://github.com/cocoindex-io/cocoindex-code>          |
| `qmd` (local hybrid search engine for project files)                   | Deep mode                                                                             | <https://github.com/tobi/qmd>                             |
| `SNYK_TOKEN` (Snyk API token — **Enterprise plan required**)           | Optional security scan                                                                | <https://docs.snyk.io/snyk-api/authentication-for-api>    |

Security scanning via Snyk is optional and requires an Enterprise plan; it does not affect your tier level.

### Platform support

**Linux and Windows** are exercised in CI on every PR (`ubuntu-latest` + `windows-latest` matrix on `validate` and `python` jobs). **macOS** works in practice — POSIX-equivalent to Linux — but isn't CI-gated; if you hit a macOS-specific bug, please [file an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues).

On Windows, SKF transparently falls back to NTFS junctions when symlink privilege isn't held, so no Developer Mode or admin rights are required. Git Bash (bundled with [Git for Windows](https://git-scm.com/download/win)), PowerShell, and WSL2 all work.

---

## Configuration

SKF has two install-time variables (defined in `src/module.yaml`), one Core Config variable inherited from BMAD, and one runtime preference:

| Variable               | Purpose                                                                                                  | Default                     |
|------------------------|----------------------------------------------------------------------------------------------------------|-----------------------------|
| `skills_output_folder` | Where generated skills are saved                                                                         | `{project-root}/skills`     |
| `forge_data_folder`    | Where workspace artifacts are stored (VS reports, evidence)                                              | `{project-root}/forge-data` |
| `output_folder`        | Where refined architecture documents are saved (used by RA workflow). *Inherited from BMAD Core Config.* | Defined by BMAD Core Config |
| `tier_override`        | Force a specific tier for comparison or testing (in `_bmad/_memory/forger-sidecar/preferences.yaml`)     | `~` (auto-detect)           |
| `headless_mode`        | Skip confirmation gates in all workflows (in `_bmad/_memory/forger-sidecar/preferences.yaml`)            | `false`                     |

Runtime configuration (tool detection, tier, and collection state) is managed by the `setup` workflow and persisted in `forge-tier.yaml`.

---

## What's next?

- [Forge-Auto](../forge-auto/) — the zero-ceremony path: one command from repo or doc URL to a verified skill
- [Campaign](../campaign/) — orchestrate many coordinated skills across sessions with dependency tracking and resume
- [Agents](../agents/) — learn about Ferris
- [Workflows](../workflows/) — the full command reference
- [Examples](../examples/) — real-world scenarios with transcripts

---

## Need help?

If you run into issues:
1. Run `/bmad-help` — analyzes your current state and suggests what to do next
   (e.g. `/bmad-help my quick skill has low confidence scores, how do I improve them?`)
   *Provided by the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) — not available in standalone SKF installations.*
2. Run `@Ferris SF` to check your tool availability and tier
3. Check `forge-tier.yaml` in your forger sidecar for your current configuration
4. If a workflow gave you friction, ask Ferris to run the health check for that session, or [open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — see [Workflow Health Check](../workflows/#terminal-step-health-check)

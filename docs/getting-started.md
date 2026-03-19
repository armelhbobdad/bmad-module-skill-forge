---
title: Getting Started
description: Installation, prerequisites, first steps, and common use cases for Skill Forge
---

# Getting Started with SKF: Skill Forge

Welcome to Skill Forge! This guide will help you get up and running.

---

## What This Module Does

Skill Forge analyzes code repositories, documentation websites, and developer discourse to build verified instruction files ("skills") for AI agents. Instead of your agent guessing API calls from training data, it follows instructions where every function, type, and pattern traces back to its source — a file and line for code, a URL for documentation, an issue or PR for discourse. Skills comply with the [agentskills.io](https://agentskills.io) open standard and work across Claude, Cursor, Copilot, and other AI tools. See the [Concepts](../concepts.md) page for definitions of key terms.

---

## Installation

There are three ways to install SKF, depending on your setup.

### Standalone (recommended for trying SKF)

```bash
npx bmad-module-skill-forge install
```

Installs SKF on its own. You'll be prompted for project name, output folders, and which IDEs to configure. The installer generates IDE-specific command files (e.g. `.claude/commands/`, `.cursor/commands/`) so workflows appear in your IDE's command palette.

### As a custom module during BMad Method installation

```bash
npx bmad-method install
```

When prompted **"Add custom modules from your computer?"**, select Yes and provide the path to the SKF `src/` folder (clone this repo first):

```
Path to custom module folder: /path/to/bmad-module-skill-forge/src/
```

This installs BMad core + SKF together with full IDE integration, manifests, and help catalog. Best when you want the complete BMad development workflow.

### Add SKF to an existing BMad project

If you already have BMad installed, you can add SKF afterward by running the standalone installer in the same directory:

```bash
npx bmad-module-skill-forge install
```

The installer detects the existing `_bmad/` directory and installs SKF alongside your current modules.

---

## Prerequisites

| Tool                                                                   | Required For               | Install                                                |
|------------------------------------------------------------------------|----------------------------|--------------------------------------------------------|
| [Node.js](https://nodejs.org/) >= 22                                   | Installation, npx commands | <https://nodejs.org>                                   |
| `gh` (GitHub CLI)                                                      | All modes                  | <https://cli.github.com>                               |
| `ast-grep`  (CLI tool for code structural search, lint, and rewriting) | Forge + Deep modes         | <https://ast-grep.github.io>                           |
| `ast-grep` MCP server (recommended alongside CLI)                      | Forge + Deep modes         | <https://github.com/ast-grep/ast-grep-mcp>             |
| `qmd` (local hybrid search engine for project files)                   | Deep mode                  | <https://github.com/tobi/qmd>                          |
| `SNYK_TOKEN` (Snyk API token — **Enterprise plan required**)           | Optional security scan     | <https://docs.snyk.io/snyk-api/authentication-for-api> |

Don't worry if you don't have all tools — SKF detects what's available and sets your tier automatically. Security scanning via Snyk is optional and requires an Enterprise plan; it does not affect your tier level.

---

## Configuration

SKF has two install-time variables (defined in `src/module.yaml`) and one runtime preference:

| Variable               | Purpose                                                                                              | Default                     |
|------------------------|------------------------------------------------------------------------------------------------------|-----------------------------|
| `skills_output_folder` | Where generated skills are saved                                                                     | `{project-root}/skills`     |
| `forge_data_folder`    | Where workspace artifacts are stored                                                                 | `{project-root}/forge-data` |
| `tier_override`        | Force a specific tier for comparison or testing (in `_bmad/_memory/forger-sidecar/preferences.yaml`) | `~` (auto-detect)           |

Runtime configuration (tool detection, tier, parallel settings) is managed by the `setup-forge` workflow in `forge-tier.yaml`.

---

## First Steps

### 1. Setup Your Forge

```
@Ferris SF
```

This detects your tools, sets your capability tier, and initializes the forge environment. You only need to do this once per project.

### 2. Generate Your First Skill

**Fastest path (Quick Skill):**
```
@Ferris QS https://github.com/bmad-code-org/BMAD-METHOD
```

Ferris reads the repository, extracts the public API, and generates a skill in under a minute.

**Full quality path:**
```
@Ferris BS    # Brief — scope and design the skill
@Ferris CS    # Create — compile from the brief
@Ferris TS    # Test — verify completeness
@Ferris EX    # Export — package for distribution
```

### 3. Stack Skill (for full projects)

```
@Ferris SS
```

Analyzes your project's dependencies and generates a consolidated stack skill with integration patterns.

---

## Common Use Cases

### My agent keeps hallucinating API calls

Your agent invents function signatures that don't exist. Generate a verified skill so it works from structural truth instead of guessing.

```
@Ferris QS https://github.com/org/library
```

The skill pins every function to its actual source location. Hallucinations stop.

### I'm adopting a new library and need my agent to use it correctly

You added a dependency but your agent doesn't know its API yet. Quick Skill resolves package names across npm, PyPI, and crates.io.

```
@Ferris QS cognee
```

Ferris resolves the package to its GitHub repo, extracts the public API, and generates a skill your agent can reference immediately.

### I want my agent to understand my entire project stack

Individual skills cover single libraries. Stack Skill maps how your dependencies interact — shared types, co-import patterns, integration points.

```
@Ferris SS
```

Ferris detects your manifests, ranks dependencies by significance, and generates a consolidated skill with cross-library integration patterns.

### I'm onboarding a large existing codebase

A brownfield repo with dozens of modules. You need to know what's worth skilling before you start.

```
@Ferris AN
```

Analyze Source scans the project, identifies skillable units, maps exports, and generates recommended briefs you can batch-create with `@Ferris CS --batch`.

### I want the highest accuracy possible

Quick mode reads source files. Forge mode adds AST parsing for structural truth. Deep mode goes further — as skills are compiled, SKF indexes curated extraction artifacts and skill briefs into QMD collections, then uses BM25 keyword search, vector semantic search, and LLM-powered re-ranking to surface context no other tool can find.

```
@Ferris SF    # Setup detects your tools and sets tier automatically
```

If `ast-grep` and `qmd` are available, Ferris activates Deep mode. Every skill gets AST-verified signatures (T1) enriched with deep knowledge search (T2) — deprecation warnings, breaking change history, common pitfalls surfaced by searching across your indexed skill artifacts.

### I maintain an OSS library and want official skills

You want maximum quality with full provenance for distribution. Use the full pipeline with Deep mode for the richest output.

```
@Ferris BS    # Scope and design the skill
@Ferris CS    # Compile — AST extraction + QMD enrichment (Deep)
@Ferris TS    # Verify completeness before publishing
@Ferris EX    # Package for distribution
```

Export with `source_authority: official`. Consumers get verified skills that update with each release.

### A dependency shipped breaking changes

Your existing skill is now out of date. Audit detects the drift, Update regenerates while preserving your manual additions.

```
@Ferris AS    # Find what changed
@Ferris US    # Regenerate — [MANUAL] sections survive
@Ferris TS    # Verify the update
```

---

## What's Next?

- Check out the [Agents Reference](../agents.md) to learn about Ferris
- Browse the [Workflows Reference](../workflows.md) to see all available commands
- See [Examples](../examples.md) for real-world usage scenarios

---

## Need Help?

If you run into issues:
1. Run `/bmad-help` — analyzes your current state and suggests what to do next
   (e.g. `/bmad-help my quick skill has low confidence scores, how do I improve them?`)
   *Provided by the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) — not available in standalone SKF installations.*
2. Run `@Ferris SF` to check your tool availability and tier
3. Check `forge-tier.yaml` in your forger sidecar for your current configuration

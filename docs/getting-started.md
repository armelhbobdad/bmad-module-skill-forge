---
title: Getting Started
description: Installation, prerequisites, first steps, and common use cases for Skill Forge
---

# Getting Started with SKF: Skill Forge

Welcome to Skill Forge! This guide will help you get up and running.

---

## What This Module Does

Skill Forge is an automated skill compiler for the AI agent ecosystem. It transforms source code into agentskills.io-compliant, version-pinned, provenance-backed agent skills. Every instruction traces to actual code — zero hallucination tolerance.

---

## Installation

If you haven't installed the module yet:

```bash
bmad install skf
```

Follow the prompts to configure the module for your needs.

---

## Prerequisites

| Tool                                                                   | Required For       | Install                     |
|------------------------------------------------------------------------|--------------------|-----------------------------|
| `gh` (GitHub CLI)                                                      | All modes          | <https://cli.github.com>      |
| `ast-grep`  (CLI tool for code structural search, lint, and rewriting) | Forge + Deep modes | <https://ast-grep.github.io>  |
| `qmd` (Query Markup Documents)                                         | Deep mode          | <https://github.com/tobi/qmd> |

Don't worry if you don't have all tools — SKF detects what's available and sets your tier automatically.

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
@Ferris QS spacetimedb
```

Ferris resolves the package to GitHub, reads the source, and generates a skill in under a minute.

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

### I need skills for my dependencies
Use Quick Skill (`QS`) for each dependency. It resolves package names to repos automatically.

### I'm onboarding a large existing codebase
Use Analyze Source (`AN`) to discover what to skill, then batch-create with Create Skill (`CS --batch`).

### I maintain an OSS library
Use Brief Skill (`BS`) + Create Skill (`CS`) for maximum quality. Export with `source_authority: official`.

### I want my agent to understand my whole project
Use Stack Skill (`SS`) for a consolidated skill with cross-library integration patterns.

---

## What's Next?

- Check out the [Agents Reference](agents.md) to learn about Ferris
- Browse the [Workflows Reference](workflows.md) to see all available commands
- See [Examples](examples.md) for real-world usage scenarios

---

## Need Help?

If you run into issues:
1. Run `@Ferris SF` to check your tool availability and tier
2. Check `forge-config.yaml` for your current configuration
3. Review the module configuration in your BMAD settings

---
title: Skill Forge (SKF)
description: AST-verified, provenance-backed agent skills from code repositories, documentation, and developer discourse
template: splash
hero:
  title: Skill Forge (SKF)
  tagline: AST-verified, provenance-backed agent skills from code repositories, documentation, and developer discourse
  actions:
    - text: Getting Started
      link: /getting-started/
      icon: right-arrow
      variant: primary
    - text: View on GitHub
      link: https://github.com/armelhbobdad/bmad-module-skill-forge
      icon: external
---

## What is Skill Forge?

Skill Forge is an automated skill compiler for the AI agent ecosystem. It transforms code repositories, documentation, and developer discourse into [agentskills.io](https://agentskills.io)-compliant, version-pinned, provenance-backed agent skills. Every instruction traces to verifiable sources — zero hallucination tolerance.

- **AST-Verified**: Structural truth via ast-grep — no guessing, no hallucination.
- **Provenance-Backed**: Every claim traces to source code with file and line references.
- **Progressive Tiers**: Quick (no setup) → Forge (ast-grep) → Deep (QMD knowledge).
- **Ecosystem-First**: Checks for official skills before generating community ones.

## Quick Install

```bash
npx bmad-module-skill-forge install
```

Then interact with the forge agent:

```
@Ferris SF    # Setup your forge environment
@Ferris QS    # Quick Skill — generate in under a minute
```

## Core Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| [Setup Forge](/workflows/#setup-forge-sf) | SF | Initialize forge, detect tools, set tier |
| [Brief Skill](/workflows/#brief-skill-bs) | BS | Scope and design a skill |
| [Create Skill](/workflows/#create-skill-cs) | CS | Compile a skill from a brief |
| [Quick Skill](/workflows/#quick-skill-qs) | QS | Fast skill, no brief needed |
| [Stack Skill](/workflows/#stack-skill-ss) | SS | Consolidated project stack skill |
| [Update Skill](/workflows/#update-skill-us) | US | Regenerate after source changes |
| [Audit Skill](/workflows/#audit-skill-as) | AS | Drift detection |
| [Test Skill](/workflows/#test-skill-ts) | TS | Verify completeness |
| [Export Skill](/workflows/#export-skill-ex) | EX | Package for distribution |
| [Analyze Source](/workflows/#analyze-source-an) | AN | Discover what to skill |

## Documentation

- **[Getting Started](getting-started.md)** — Installation, prerequisites, first steps
- **[Agents](agents.md)** — Ferris agent: modes, capabilities, communication style
- **[Workflows](workflows.md)** — All 10 workflows with commands and connection diagram
- **[Examples](examples.md)** — Real-world scenarios, tips, and troubleshooting

## Support

- **Issues**: [GitHub Issues](https://github.com/armelhbobdad/bmad-module-skill-forge/issues)
